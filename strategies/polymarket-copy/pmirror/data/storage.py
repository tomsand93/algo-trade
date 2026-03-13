"""
Parquet storage for pmirror trade data.

This module provides efficient read/write operations for storing normalized
trade data in parquet format. Parquet is ideal for this use case because:
- Columnar storage for fast filtering by date, maker, market
- Compression for smaller file sizes
- Type preservation for accurate data representation
"""

from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from pmirror.config import get_settings
from pmirror.domain.normalize import normalize_trades, _empty_trade_dataframe


class TradeStorage:
    """
    Manages storage and retrieval of trade data in parquet format.

    Trades are organized by date and optionally by wallet/market for
    efficient querying during backtesting.
    """

    def __init__(self, settings=None):
        """
        Initialize the storage manager.

        Args:
            settings: Optional settings object (uses get_settings() if not provided)
        """
        self.config = settings if settings else get_settings()
        self.clean_dir = self.config.data.clean_data_dir
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create storage directories if they don't exist."""
        self.clean_dir.mkdir(parents=True, exist_ok=True)

    def save_trades(
        self,
        df: pd.DataFrame,
        path: str | Path | None = None,
        compression: str = "snappy",
    ) -> Path:
        """
        Save trade DataFrame to parquet file.

        Args:
            df: Trade DataFrame (from normalize_trades())
            path: Output file path (defaults to data/clean/trades.parquet)
            compression: Compression codec ('snappy', 'gzip', 'brotli', 'lz4')

        Returns:
            Path to the saved file

        Raises:
            ValueError: If DataFrame is empty or missing required columns
        """
        if df.empty:
            raise ValueError("Cannot save empty DataFrame")

        required_columns = ["transaction_hash", "timestamp", "maker", "side", "price", "size", "market_id"]
        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            raise ValueError(f"DataFrame missing required columns: {missing}")

        if path is None:
            path = self.clean_dir / "trades.parquet"
        else:
            path = Path(path)

        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Convert timestamp to datetime64[ns, UTC] for consistent parquet storage
        df_to_save = df.copy()
        if "timestamp" in df_to_save.columns:
            df_to_save["timestamp"] = pd.to_datetime(df_to_save["timestamp"])
            if df_to_save["timestamp"].dt.tz is None:
                df_to_save["timestamp"] = df_to_save["timestamp"].dt.tz_localize("UTC")
            else:
                df_to_save["timestamp"] = df_to_save["timestamp"].dt.tz_convert("UTC")

        # Write to parquet
        df_to_save.to_parquet(path, compression=compression, index=False)

        return path

    def load_trades(
        self,
        path: str | Path | None = None,
        filters: dict | None = None,
    ) -> pd.DataFrame:
        """
        Load trades from parquet file.

        Args:
            path: Path to parquet file (defaults to data/clean/trades.parquet)
            filters: Optional filters for efficient loading
                    (e.g., {"market_id": "0x123", "side": "buy"})

        Returns:
            DataFrame of trades

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        if path is None:
            path = self.clean_dir / "trades.parquet"
        else:
            path = Path(path)

        if not path.exists():
            return _empty_trade_dataframe()

        # Read with filters if provided
        if filters:
            # Convert filters to pyarrow format for efficient filtering
            pf = pq.ParquetFile(path)
            df = pf.read(filters=self._pyarrow_filters(filters)).to_pandas()
        else:
            df = pd.read_parquet(path)

        # Ensure timezone awareness
        if "timestamp" in df.columns and df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")

        return df

    def append_trades(
        self,
        df: pd.DataFrame,
        path: str | Path | None = None,
        deduplicate: bool = True,
    ) -> Path:
        """
        Append new trades to existing parquet file.

        Args:
            df: New trade DataFrame to append
            path: Path to parquet file
            deduplicate: If True, remove duplicates by transaction_hash

        Returns:
            Path to the saved file
        """
        # Load existing data
        existing = self.load_trades(path)

        # Merge and deduplicate
        from pmirror.domain.normalize import merge_trade_dataframes

        merged = merge_trade_dataframes([existing, df], remove_duplicates=deduplicate)

        # Save back
        return self.save_trades(merged, path)

    def save_trades_by_date(
        self,
        df: pd.DataFrame,
        base_dir: str | Path | None = None,
    ) -> dict[str, Path]:
        """
        Save trades partitioned by date for efficient querying.

        Creates files like: data/clean/2024/01/2024-01-15.parquet

        Args:
            df: Trade DataFrame
            base_dir: Base directory for partitioned files

        Returns:
            Dictionary mapping date string to file path
        """
        if df.empty:
            return {}

        if base_dir is None:
            base_dir = self.clean_dir / "by_date"
        else:
            base_dir = Path(base_dir)

        # Extract date from timestamp
        df_copy = df.copy()
        df_copy["date"] = pd.to_datetime(df_copy["timestamp"]).dt.date

        saved_paths = {}
        for date, group in df_copy.groupby("date"):
            date_str = str(date)
            year = date_str[:4]
            month = date_str[5:7]

            # Create path: base_dir/YYYY/MM/YYYY-MM-DD.parquet
            file_path = base_dir / year / month / f"{date_str}.parquet"
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Drop date column before saving
            group_to_save = group.drop(columns=["date"])
            group_to_save.to_parquet(file_path, index=False, compression="snappy")

            saved_paths[date_str] = file_path

        return saved_paths

    def load_trades_by_date(
        self,
        start_date: str | datetime,
        end_date: str | datetime,
        base_dir: str | Path | None = None,
    ) -> pd.DataFrame:
        """
        Load trades for a date range from partitioned files.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            base_dir: Base directory for partitioned files

        Returns:
            Combined DataFrame of trades for the date range
        """
        if base_dir is None:
            base_dir = self.clean_dir / "by_date"
        else:
            base_dir = Path(base_dir)

        # Convert dates to strings
        if isinstance(start_date, datetime):
            start_date = start_date.strftime("%Y-%m-%d")
        if isinstance(end_date, datetime):
            end_date = end_date.strftime("%Y-%m-%d")

        # Collect file paths
        date_range = pd.date_range(start_date, end_date)
        dataframes = []

        for date in date_range:
            date_str = date.strftime("%Y-%m-%d")
            year = date_str[:4]
            month = date_str[5:7]
            file_path = base_dir / year / month / f"{date_str}.parquet"

            if file_path.exists():
                df = pd.read_parquet(file_path)
                dataframes.append(df)

        if not dataframes:
            return _empty_trade_dataframe()

        # Combine all dataframes
        result = pd.concat(dataframes, ignore_index=True)

        # Ensure timezone awareness
        if "timestamp" in result.columns and result["timestamp"].dt.tz is None:
            result["timestamp"] = result["timestamp"].dt.tz_localize("UTC")

        return result

    def save_wallet_trades(
        self,
        df: pd.DataFrame,
        wallet: str,
        base_dir: str | Path | None = None,
    ) -> Path:
        """
        Save trades for a specific wallet.

        Creates file: data/clean/wallets/0x123...abc.parquet

        Args:
            df: Trade DataFrame for a single wallet
            wallet: Wallet address
            base_dir: Base directory for wallet files

        Returns:
            Path to saved file
        """
        if base_dir is None:
            base_dir = self.clean_dir / "wallets"
        else:
            base_dir = Path(base_dir)

        # Normalize wallet address
        wallet = wallet.lower()

        # Create file path
        file_path = base_dir / f"{wallet}.parquet"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        df.to_parquet(file_path, index=False, compression="snappy")

        return file_path

    def load_wallet_trades(
        self,
        wallet: str,
        base_dir: str | Path | None = None,
    ) -> pd.DataFrame:
        """
        Load trades for a specific wallet.

        Args:
            wallet: Wallet address
            base_dir: Base directory for wallet files

        Returns:
            DataFrame of trades for the wallet
        """
        if base_dir is None:
            base_dir = self.clean_dir / "wallets"
        else:
            base_dir = Path(base_dir)

        wallet = wallet.lower()
        file_path = base_dir / f"{wallet}.parquet"

        if not file_path.exists():
            return _empty_trade_dataframe()

        df = pd.read_parquet(file_path)

        # Ensure timezone awareness
        if "timestamp" in df.columns and df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")

        return df

    def list_wallets(
        self,
        base_dir: str | Path | None = None,
    ) -> list[str]:
        """
        List all wallets with saved trade data.

        Args:
            base_dir: Base directory for wallet files

        Returns:
            List of wallet addresses
        """
        if base_dir is None:
            base_dir = self.clean_dir / "wallets"
        else:
            base_dir = Path(base_dir)

        if not base_dir.exists():
            return []

        wallets = []
        for file_path in base_dir.glob("*.parquet"):
            wallet = file_path.stem  # Filename without .parquet
            wallets.append(wallet)

        return sorted(wallets)

    def get_storage_info(
        self,
        path: str | Path | None = None,
    ) -> dict:
        """
        Get information about stored trade data.

        Args:
            path: Path to parquet file

        Returns:
            Dictionary with storage statistics
        """
        if path is None:
            path = self.clean_dir / "trades.parquet"
        else:
            path = Path(path)

        info = {
            "exists": path.exists(),
            "path": str(path),
            "size_bytes": 0,
            "trade_count": 0,
            "date_range": None,
        }

        if not path.exists():
            return info

        info["size_bytes"] = path.stat().st_size

        # Read metadata without loading full data
        pf = pq.ParquetFile(path)
        info["trade_count"] = pf.metadata.num_rows

        # Get date range from metadata if available
        try:
            df = pd.read_parquet(path, columns=["timestamp"])
            if not df.empty:
                info["date_range"] = (df["timestamp"].min(), df["timestamp"].max())
        except Exception:
            pass

        return info

    def _pyarrow_filters(self, filters: dict) -> list:
        """
        Convert filter dict to pyarrow filter format.

        Args:
            filters: Dict of column -> value mappings

        Returns:
            Pyarrow-compatible filter list
        """
        result = []
        for column, value in filters.items():
            if isinstance(value, list):
                # IN clause: [(column, "in", value)]
                result.append((column, "in", value))
            else:
                # Equality: [(column, "==", value)]
                result.append((column, "==", value))

        return result

    def delete_file(
        self,
        path: str | Path,
    ) -> bool:
        """
        Delete a parquet file.

        Args:
            path: Path to file to delete

        Returns:
            True if deleted, False if didn't exist
        """
        path = Path(path)
        if path.exists():
            path.unlink()
            return True
        return False

    def clear_all(self, base_dir: str | Path | None = None) -> int:
        """
        Delete all parquet files in the clean data directory.

        WARNING: This will delete all stored trade data!

        Args:
            base_dir: Directory to clear (defaults to clean data dir)

        Returns:
            Number of files deleted
        """
        if base_dir is None:
            base_dir = self.clean_dir
        else:
            base_dir = Path(base_dir)

        if not base_dir.exists():
            return 0

        count = 0
        for file_path in base_dir.rglob("*.parquet"):
            file_path.unlink()
            count += 1

        return count


def save_markets(
    markets: list,
    path: str | Path | None = None,
    settings=None,
) -> Path:
    """
    Save market metadata to parquet.

    Args:
        markets: List of Market domain models or dicts
        path: Output file path
        settings: Optional settings object

    Returns:
        Path to saved file
    """
    config = settings if settings else get_settings()

    if path is None:
        path = config.data.clean_data_dir / "markets.parquet"
    else:
        path = Path(path)

    # Convert to list of dicts if Market objects
    if markets and hasattr(markets[0], "model_dump"):
        data = [m.model_dump() for m in markets]
    elif markets and hasattr(markets[0], "dict"):
        data = [m.dict() for m in markets]
    else:
        data = markets

    df = pd.DataFrame(data)
    df.to_parquet(path, index=False, compression="snappy")

    return path


def load_markets(
    path: str | Path | None = None,
    settings=None,
) -> pd.DataFrame:
    """
    Load market metadata from parquet.

    Args:
        path: Path to parquet file
        settings: Optional settings object

    Returns:
        DataFrame of markets
    """
    config = settings if settings else get_settings()

    if path is None:
        path = config.data.clean_data_dir / "markets.parquet"
    else:
        path = Path(path)

    if not path.exists():
        return pd.DataFrame(columns=[
            "condition_id", "question", "outcomes", "end_time",
            "resolution", "description", "volume", "liquidity",
        ])

    return pd.read_parquet(path)
