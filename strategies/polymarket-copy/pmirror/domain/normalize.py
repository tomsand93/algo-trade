"""
Trade data normalization for pmirror.

This module converts raw trade data from the Polymarket API into a clean,
normalized format suitable for parquet storage and backtesting.

Key features:
- Deduplication by transaction_hash
- Data validation and quality checks
- Conversion to pandas DataFrame for parquet storage
- Handling of timezone and timestamp normalization
"""

from datetime import datetime, timezone
from collections import defaultdict
from typing import Literal

import pandas as pd
import numpy as np

from pmirror.domain import Trade
from pmirror.config import get_settings


class DuplicateTradeError(Exception):
    """Raised when duplicate trades are detected."""

    pass


class ValidationError(Exception):
    """Raised when trade data validation fails."""

    pass


def normalize_trades(
    trades: list[Trade],
    remove_duplicates: bool = True,
    validate: bool = True,
) -> pd.DataFrame:
    """
    Normalize a list of Trade domain models to a pandas DataFrame.

    The DataFrame is suitable for parquet storage with consistent types and
    column names.

    Args:
        trades: List of Trade domain models
        remove_duplicates: If True, remove duplicate trades by transaction_hash
        validate: If True, validate trade data before normalization

    Returns:
        DataFrame with normalized trade data

    Raises:
        ValidationError: If validation fails and validate=True
        DuplicateTradeError: If duplicates found and remove_duplicates=False
    """
    if not trades:
        return _empty_trade_dataframe()

    if validate:
        validation_errors = validate_trades(trades)
        if validation_errors:
            raise ValidationError(
                f"Trade validation failed with {len(validation_errors)} errors: "
                f"{validation_errors[:3]}..."
            )

    # Convert trades to dict format
    records = []
    for trade in trades:
        record = {
            "transaction_hash": trade.transaction_hash,
            "timestamp": _normalize_timestamp(trade.timestamp),
            "maker": trade.maker,
            "taker": trade.taker,
            "side": trade.side,
            "outcome": trade.outcome,
            "price": trade.price,
            "size": trade.size,
            "market_id": trade.market_id,
            "shares": trade.shares,
            "fee": trade.fee,
        }
        records.append(record)

    df = pd.DataFrame(records)

    # Set consistent column order
    df = _reorder_columns(df)

    # Handle deduplication
    if remove_duplicates:
        df = _deduplicate_trades(df)

    return df


def validate_trades(trades: list[Trade]) -> list[str]:
    """
    Validate a list of trades and return list of error messages.

    Checks performed:
    - Required fields are present and non-empty
    - Price is within valid range (0-1)
    - Size is positive
    - Timestamp is not in the future
    - Transaction hash is valid format (0x...)

    Args:
        trades: List of Trade domain models

    Returns:
        List of error messages (empty if all valid)
    """
    errors = []
    now = datetime.now(timezone.utc)

    for i, trade in enumerate(trades):
        prefix = f"Trade #{i} ({trade.transaction_hash[:16]}...)"

        # Check transaction hash format
        if not trade.transaction_hash or not trade.transaction_hash.startswith("0x"):
            errors.append(f"{prefix}: Invalid transaction_hash format")

        # Check maker address
        if not trade.maker or not trade.maker.startswith("0x"):
            errors.append(f"{prefix}: Invalid maker address")

        # Check side
        if trade.side not in ("buy", "sell"):
            errors.append(f"{prefix}: Invalid side '{trade.side}'")

        # Check price range
        if not (0 <= trade.price <= 1):
            errors.append(f"{prefix}: Price {trade.price} outside valid range [0, 1]")

        # Check size
        if trade.size <= 0:
            errors.append(f"{prefix}: Size must be positive, got {trade.size}")

        # Check timestamp not in future (with 5 minute tolerance for clock skew)
        if trade.timestamp > now + pd.Timedelta(minutes=5):
            errors.append(f"{prefix}: Timestamp {trade.timestamp} is in the future")

        # Check market_id
        if not trade.market_id or not trade.market_id.startswith("0x"):
            errors.append(f"{prefix}: Invalid market_id")

        # Check outcome
        if not trade.outcome:
            errors.append(f"{prefix}: Empty outcome")

        # Check shares computed correctly
        expected_shares = trade.size / trade.price if trade.price > 0 else 0
        if trade.shares is not None and abs(trade.shares - expected_shares) > 0.01:
            errors.append(
                f"{prefix}: Shares mismatch. Expected {expected_shares:.2f}, "
                f"got {trade.shares:.2f}"
            )

    return errors


def deduplicate_trades(
    trades: list[Trade],
    keep: Literal["first", "last"] = "first",
) -> list[Trade]:
    """
    Remove duplicate trades from a list.

    Duplicates are identified by transaction_hash. If multiple trades have
    the same transaction_hash, only one is kept.

    Args:
        trades: List of Trade domain models
        keep: Which duplicate to keep - "first" or "last"

    Returns:
        Deduplicated list of trades

    Raises:
        DuplicateTradeError: If duplicates are found
    """
    seen = {}
    duplicates = []

    for trade in trades:
        tx_hash = trade.transaction_hash
        if tx_hash in seen:
            duplicates.append(tx_hash)
            if keep == "last":
                seen[tx_hash] = trade
        else:
            seen[tx_hash] = trade

    if duplicates:
        unique_duplicates = set(duplicates)
        raise DuplicateTradeError(
            f"Found {len(unique_duplicates)} duplicate trades: "
            f"{list(unique_duplicates)[:3]}..."
        )

    return list(seen.values())


def deduplicate_dataframe(
    df: pd.DataFrame,
    keep: Literal["first", "last"] = "first",
) -> tuple[pd.DataFrame, int]:
    """
    Remove duplicate rows from a trade DataFrame.

    Args:
        df: Trade DataFrame
        keep: Which duplicate to keep - "first" or "last"

    Returns:
        Tuple of (deduplicated DataFrame, number of duplicates removed)
    """
    if df.empty:
        return df, 0

    before = len(df)
    df = df.drop_duplicates(subset=["transaction_hash"], keep=keep)
    after = len(df)

    return df, before - after


def aggregate_trades_by_market(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Aggregate trade statistics by market.

    Args:
        df: Trade DataFrame

    Returns:
        DataFrame with one row per market containing aggregated statistics
    """
    if df.empty:
        return pd.DataFrame(
            columns=[
                "market_id",
                "trade_count",
                "total_volume",
                "avg_price",
                "first_trade",
                "last_trade",
            ]
        )

    agg = (
        df.groupby("market_id")
        .agg(
            trade_count=pd.NamedAgg(column="transaction_hash", aggfunc="count"),
            total_volume=pd.NamedAgg(column="size", aggfunc="sum"),
            avg_price=pd.NamedAgg(column="price", aggfunc="mean"),
            first_trade=pd.NamedAgg(column="timestamp", aggfunc="min"),
            last_trade=pd.NamedAgg(column="timestamp", aggfunc="max"),
        )
        .reset_index()
    )

    return agg


def filter_trades(
    df: pd.DataFrame,
    start: datetime | None = None,
    end: datetime | None = None,
    makers: list[str] | None = None,
    market_ids: list[str] | None = None,
    min_size: float | None = None,
    sides: list[str] | None = None,
) -> pd.DataFrame:
    """
    Filter trades DataFrame by various criteria.

    Args:
        df: Trade DataFrame
        start: Only include trades after this timestamp (inclusive)
        end: Only include trades before this timestamp (exclusive)
        makers: Only include trades from these maker addresses
        market_ids: Only include trades in these markets
        min_size: Only include trades with size >= this value
        sides: Only include trades with these sides ("buy", "sell")

    Returns:
        Filtered DataFrame
    """
    if df.empty:
        return df

    result = df.copy()

    if start is not None:
        start_normalized = pd.Timestamp(_normalize_timestamp(start))
        result = result[result["timestamp"] >= start_normalized]

    if end is not None:
        end_normalized = pd.Timestamp(_normalize_timestamp(end))
        result = result[result["timestamp"] < end_normalized]

    if makers:
        result = result[result["maker"].isin(makers)]

    if market_ids:
        result = result[result["market_id"].isin(market_ids)]

    if min_size is not None:
        result = result[result["size"] >= min_size]

    if sides:
        result = result[result["side"].isin(sides)]

    return result


def compute_trade_statistics(df: pd.DataFrame) -> dict:
    """
    Compute summary statistics for a trade DataFrame.

    Args:
        df: Trade DataFrame

    Returns:
        Dictionary of statistics
    """
    if df.empty:
        return {
            "total_trades": 0,
            "total_volume": 0.0,
            "unique_makers": 0,
            "unique_markets": 0,
            "buy_count": 0,
            "sell_count": 0,
            "avg_trade_size": 0.0,
            "date_range": None,
        }

    return {
        "total_trades": len(df),
        "total_volume": df["size"].sum(),
        "unique_makers": df["maker"].nunique(),
        "unique_markets": df["market_id"].nunique(),
        "buy_count": (df["side"] == "buy").sum(),
        "sell_count": (df["side"] == "sell").sum(),
        "avg_trade_size": df["size"].mean(),
        "date_range": (df["timestamp"].min(), df["timestamp"].max()),
    }


def _normalize_timestamp(ts: datetime) -> pd.Timestamp:
    """
    Normalize a datetime to UTC pandas Timestamp.

    Ensures timezone awareness and consistent representation.
    """
    pd_ts = pd.Timestamp(ts)
    if pd_ts.tz is None:
        # Assume UTC if naive
        return pd_ts.tz_localize(timezone.utc)
    return pd_ts.tz_convert(timezone.utc)


def _deduplicate_trades(df: pd.DataFrame) -> pd.DataFrame:
    """
    Internal deduplication by transaction_hash.
    """
    df, _ = deduplicate_dataframe(df, keep="first")
    return df


def _reorder_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure consistent column order.
    """
    column_order = [
        "transaction_hash",
        "timestamp",
        "maker",
        "taker",
        "side",
        "outcome",
        "price",
        "size",
        "shares",
        "fee",
        "market_id",
    ]

    # Only include columns that exist
    columns = [c for c in column_order if c in df.columns]

    # Add any extra columns at the end
    extra_columns = [c for c in df.columns if c not in columns]
    columns.extend(extra_columns)

    return df[columns]


def _empty_trade_dataframe() -> pd.DataFrame:
    """
    Return an empty DataFrame with correct schema.
    """
    return pd.DataFrame(
        columns=[
            "transaction_hash",
            "timestamp",
            "maker",
            "taker",
            "side",
            "outcome",
            "price",
            "size",
            "shares",
            "fee",
            "market_id",
        ]
    )


def merge_trade_dataframes(
    dfs: list[pd.DataFrame],
    remove_duplicates: bool = True,
) -> pd.DataFrame:
    """
    Merge multiple trade DataFrames into one.

    Args:
        dfs: List of trade DataFrames
        remove_duplicates: If True, remove duplicates after merge

    Returns:
        Merged DataFrame
    """
    if not dfs:
        return _empty_trade_dataframe()

    # Filter out empty DataFrames
    non_empty = [df for df in dfs if not df.empty]

    if not non_empty:
        return _empty_trade_dataframe()

    result = pd.concat(non_empty, ignore_index=True)

    if remove_duplicates:
        result = _deduplicate_trades(result)

    # Sort by timestamp
    result = result.sort_values("timestamp").reset_index(drop=True)

    return result


# =============================================================================
# Parquet Storage Functions
# =============================================================================

def save_trades_parquet(trades: list[Trade], path: str) -> None:
    """
    Save a list of Trade models to a parquet file.

    This function normalizes trades to a DataFrame and saves to parquet.
    It creates parent directories if they don't exist.

    Args:
        trades: List of Trade domain models
        path: Path to parquet file (will be created/overwritten)

    Raises:
        IOError: If file cannot be written
    """
    from pathlib import Path

    # Ensure parent directory exists
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    # Normalize trades to DataFrame
    df = normalize_trades(trades, validate=False, remove_duplicates=False)

    # Save to parquet
    df.to_parquet(path, index=False)


def load_trades_parquet(path: str) -> list[Trade]:
    """
    Load trades from a parquet file.

    Reads a parquet file and converts rows back to Trade domain models.

    Args:
        path: Path to parquet file

    Returns:
        List of Trade domain models

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    from pathlib import Path

    path_obj = Path(path)
    if not path_obj.exists():
        raise FileNotFoundError(f"Parquet file not found: {path}")

    # Read parquet
    df = pd.read_parquet(path)

    # Convert DataFrame rows back to Trade models
    trades = []
    for _, row in df.iterrows():
        trade = Trade(
            transaction_hash=row["transaction_hash"],
            timestamp=pd.to_datetime(row["timestamp"]),
            maker=row["maker"],
            taker=row.get("taker", None) if pd.notna(row.get("taker")) else None,
            side=row["side"],
            outcome=row["outcome"],
            price=float(row["price"]),
            size=float(row["size"]),
            market_id=row["market_id"],
            shares=float(row["shares"]) if pd.notna(row.get("shares")) else None,
            fee=float(row["fee"]) if pd.notna(row.get("fee")) else None,
        )
        trades.append(trade)

    return trades


def save_dataframe_parquet(
    df: pd.DataFrame,
    path: str,
    mode: Literal["overwrite", "append"] = "overwrite",
) -> None:
    """
    Save a DataFrame to a parquet file with support for append mode.

    Args:
        df: DataFrame to save (must have trade data columns)
        path: Path to parquet file
        mode: "overwrite" to replace existing file, "append" to add data

    Raises:
        ValueError: If mode is not "overwrite" or "append"
        IOError: If file cannot be written
    """
    from pathlib import Path

    if mode not in ("overwrite", "append"):
        raise ValueError(f"Invalid mode: {mode}. Use 'overwrite' or 'append'.")

    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    if mode == "append" and path_obj.exists():
        # Load existing data and append
        existing_df = pd.read_parquet(path)
        combined_df = pd.concat([existing_df, df], ignore_index=True)
        # Remove duplicates that may have been introduced
        combined_df = combined_df.drop_duplicates(
            subset=["transaction_hash"], keep="last"
        )
        combined_df = combined_df.sort_values("timestamp").reset_index(drop=True)
        combined_df.to_parquet(path, index=False)
    else:
        # Overwrite (or file doesn't exist)
        df.to_parquet(path, index=False)


def load_dataframe_parquet(path: str) -> pd.DataFrame:
    """
    Load a DataFrame from a parquet file.

    Args:
        path: Path to parquet file

    Returns:
        DataFrame with trade data

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    from pathlib import Path

    path_obj = Path(path)
    if not path_obj.exists():
        raise FileNotFoundError(f"Parquet file not found: {path}")

    return pd.read_parquet(path)
