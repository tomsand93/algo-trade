"""
Tests for trade data normalization.
"""

from datetime import datetime, timezone, timedelta

import pandas as pd
import pytest
import pytz

from pmirror.domain import Trade
from pmirror.domain.normalize import (
    normalize_trades,
    validate_trades,
    deduplicate_trades,
    deduplicate_dataframe,
    aggregate_trades_by_market,
    filter_trades,
    compute_trade_statistics,
    merge_trade_dataframes,
    DuplicateTradeError,
    ValidationError,
)


def _create_trade(**kwargs) -> Trade:
    """Helper to create Trade objects, bypassing validation if needed."""
    defaults = {
        "transaction_hash": "0x1",
        "timestamp": datetime.now(timezone.utc),
        "maker": "0xabc",
        "side": "buy",
        "outcome": "yes",
        "price": 0.5,
        "size": 100,
        "market_id": "0xm",
    }
    defaults.update(kwargs)
    return Trade(**defaults)


class TestNormalizeTrades:
    """Tests for normalize_trades function."""

    def test_empty_list_returns_empty_dataframe(self):
        """Empty trade list should return empty DataFrame with correct columns."""
        df = normalize_trades([])
        assert df.empty
        assert "transaction_hash" in df.columns
        assert "timestamp" in df.columns
        assert "price" in df.columns

    def test_normalize_single_trade(self):
        """Should convert single trade to DataFrame."""
        trade = Trade(
            transaction_hash="0xabcd",
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            maker="0xabc123",
            side="buy",
            outcome="yes",
            price=0.65,
            size=100.0,
            market_id="0xmarket",
        )

        df = normalize_trades(trades=[trade], validate=False, remove_duplicates=False)

        assert len(df) == 1
        assert df.iloc[0]["transaction_hash"] == "0xabcd"
        assert df.iloc[0]["price"] == 0.65
        assert df.iloc[0]["side"] == "buy"

    def test_normalize_multiple_trades(self):
        """Should convert multiple trades to DataFrame."""
        trades = [
            Trade(
                transaction_hash=f"0x{i}",
                timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
                maker="0xabc",
                side="buy",
                outcome="yes",
                price=0.5 + (i * 0.05),
                size=100.0,
                market_id="0xm",
            )
            for i in range(5)
        ]

        df = normalize_trades(trades=trades, validate=False, remove_duplicates=False)

        assert len(df) == 5

    def test_column_order_is_consistent(self):
        """DataFrame should have consistent column order."""
        trade = Trade(
            transaction_hash="0x1",
            timestamp=datetime.now(timezone.utc),
            maker="0xabc",
            side="buy",
            outcome="yes",
            price=0.5,
            size=100,
            market_id="0xm",
        )

        df = normalize_trades([trade], validate=False, remove_duplicates=False)

        columns = list(df.columns)
        assert columns[0] == "transaction_hash"
        assert "timestamp" in columns
        assert "price" in columns
        assert "size" in columns


class TestValidateTrades:
    """Tests for validate_trades function."""

    def test_valid_trade_passes(self):
        """Valid trade should pass validation."""
        trade = Trade(
            transaction_hash="0xabcd1234",
            timestamp=datetime.now(timezone.utc),
            maker="0xabc123",
            side="buy",
            outcome="yes",
            price=0.65,
            size=100.0,
            market_id="0xmarket",
        )

        errors = validate_trades([trade])
        assert errors == []

    def test_invalid_transaction_hash(self):
        """Should catch invalid transaction hash."""
        trade = Trade(
            transaction_hash="invalid",  # Missing 0x prefix
            timestamp=datetime.now(timezone.utc),
            maker="0xabc",
            side="buy",
            outcome="yes",
            price=0.5,
            size=100,
            market_id="0xm",
        )

        errors = validate_trades([trade])
        assert len(errors) > 0
        assert "Invalid transaction_hash" in errors[0]

    def test_invalid_maker_address(self):
        """Should catch invalid maker address."""
        # Use model_construct to bypass Pydantic validation
        trade = Trade.model_construct(
            transaction_hash="0x1",
            timestamp=datetime.now(timezone.utc),
            maker="",  # Empty
            side="buy",
            outcome="yes",
            price=0.5,
            size=100,
            market_id="0xm",
        )

        errors = validate_trades([trade])
        assert len(errors) > 0
        assert "maker" in errors[0].lower()

    def test_price_out_of_range(self):
        """Should catch price outside [0, 1]."""
        trade1 = Trade.model_construct(
            transaction_hash="0x1",
            timestamp=datetime.now(timezone.utc),
            maker="0xabc",
            side="buy",
            outcome="yes",
            price=1.5,  # Too high
            size=100,
            market_id="0xm",
        )

        trade2 = Trade.model_construct(
            transaction_hash="0x2",
            timestamp=datetime.now(timezone.utc),
            maker="0xabc",
            side="buy",
            outcome="yes",
            price=-0.1,  # Negative
            size=100,
            market_id="0xm",
        )

        errors = validate_trades([trade1, trade2])
        assert len(errors) == 2

    def test_negative_size(self):
        """Should catch non-positive size."""
        trade = Trade.model_construct(
            transaction_hash="0x1",
            timestamp=datetime.now(timezone.utc),
            maker="0xabc",
            side="buy",
            outcome="yes",
            price=0.5,
            size=0,  # Must be > 0
            market_id="0xm",
        )

        errors = validate_trades([trade])
        assert len(errors) > 0
        assert "Size" in errors[0]

    def test_future_timestamp(self):
        """Should catch timestamps in the future."""
        future = datetime.now(timezone.utc) + timedelta(minutes=10)

        trade = Trade(
            transaction_hash="0x1",
            timestamp=future,
            maker="0xabc",
            side="buy",
            outcome="yes",
            price=0.5,
            size=100,
            market_id="0xm",
        )

        errors = validate_trades([trade])
        assert len(errors) > 0
        assert "future" in errors[0].lower()

    def test_multiple_errors_aggregated(self):
        """Should return all errors from multiple trades."""
        trades = [
            Trade.model_construct(
                transaction_hash="bad",
                timestamp=datetime.now(timezone.utc),
                maker="0xabc",
                side="buy",
                outcome="yes",
                price=1.5,
                size=100,
                market_id="0xm",
            ),
            Trade.model_construct(
                transaction_hash="0x2",
                timestamp=datetime.now(timezone.utc),
                maker="",
                side="invalid",
                outcome="",
                price=0.5,
                size=-10,
                market_id="0xm",
            ),
        ]

        errors = validate_trades(trades)
        assert len(errors) > 2

    def test_shares_computation_validation(self):
        """Should validate shares computation."""
        trade = Trade(
            transaction_hash="0x1",
            timestamp=datetime.now(timezone.utc),
            maker="0xabc",
            side="buy",
            outcome="yes",
            price=0.5,
            size=100,
            shares=300,  # Should be 200
            market_id="0xm",
        )

        errors = validate_trades([trade])
        assert len(errors) > 0
        assert "Shares" in errors[0]


class TestDeduplicateTrades:
    """Tests for deduplicate_trades function."""

    def test_no_duplicates(self):
        """Should return original list if no duplicates."""
        trades = [
            Trade(
                transaction_hash=f"0x{i}",
                timestamp=datetime.now(timezone.utc),
                maker="0xabc",
                side="buy",
                outcome="yes",
                price=0.5,
                size=100,
                market_id="0xm",
            )
            for i in range(5)
        ]

        result = deduplicate_trades(trades)
        assert len(result) == 5

    def test_raises_on_duplicates(self):
        """Should raise DuplicateTradeError when duplicates found."""
        trades = [
            Trade(
                transaction_hash="0xabc",  # Same hash
                timestamp=datetime.now(timezone.utc),
                maker="0xabc",
                side="buy",
                outcome="yes",
                price=0.5,
                size=100,
                market_id="0xm",
            ),
            Trade(
                transaction_hash="0xabc",  # Duplicate
                timestamp=datetime.now(timezone.utc) + timedelta(seconds=1),
                maker="0xdef",
                side="sell",
                outcome="no",
                price=0.5,
                size=50,
                market_id="0xm",
            ),
        ]

        with pytest.raises(DuplicateTradeError) as exc_info:
            deduplicate_trades(trades)

        assert "duplicate" in str(exc_info.value).lower()

    def test_keep_first(self):
        """When keep='first', should keep first occurrence."""
        trades = [
            Trade(
                transaction_hash="0xdup",
                timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                maker="0xfirst",
                side="buy",
                outcome="yes",
                price=0.5,
                size=100,
                market_id="0xm",
            ),
            Trade(
                transaction_hash="0xdup",
                timestamp=datetime(2024, 1, 1, 12, 0, 1, tzinfo=timezone.utc),
                maker="0xsecond",
                side="buy",
                outcome="yes",
                price=0.6,
                size=200,
                market_id="0xm",
            ),
        ]

        # First check it raises
        with pytest.raises(DuplicateTradeError):
            deduplicate_trades(trades, keep="first")


class TestDeduplicateDataframe:
    """Tests for deduplicate_dataframe function."""

    def test_deduplicate_empty_dataframe(self):
        """Empty dataframe should return empty with 0 duplicates."""
        df = pd.DataFrame(columns=["transaction_hash", "price"])
        result, count = deduplicate_dataframe(df)
        assert result.empty
        assert count == 0

    def test_deduplicate_removes_duplicates(self):
        """Should remove duplicate rows by transaction_hash."""
        df = pd.DataFrame({
            "transaction_hash": ["0x1", "0x2", "0x1", "0x3"],
            "price": [0.5, 0.6, 0.5, 0.7],
        })

        result, count = deduplicate_dataframe(df, keep="first")

        assert len(result) == 3
        assert count == 1
        assert list(result["transaction_hash"].values) == ["0x1", "0x2", "0x3"]

    def test_keep_last(self):
        """Should keep last occurrence when keep='last'."""
        df = pd.DataFrame({
            "transaction_hash": ["0x1", "0x2", "0x1"],
            "price": [0.5, 0.6, 0.55],
        })

        result, count = deduplicate_dataframe(df, keep="last")

        assert len(result) == 2
        # Last 0x1 should have price 0.55
        assert result[result["transaction_hash"] == "0x1"]["price"].values[0] == 0.55


class TestAggregateTradesByMarket:
    """Tests for aggregate_trades_by_market function."""

    def test_empty_dataframe(self):
        """Empty DataFrame should return empty aggregation."""
        df = pd.DataFrame(columns=["transaction_hash", "market_id", "size", "price", "timestamp"])
        result = aggregate_trades_by_market(df)

        assert result.empty
        assert "market_id" in result.columns

    def test_aggregates_correctly(self):
        """Should compute correct aggregations."""
        df = pd.DataFrame({
            "transaction_hash": ["0x1", "0x2", "0x3"],
            "market_id": ["0xm1", "0xm1", "0xm2"],
            "size": [100.0, 50.0, 200.0],
            "price": [0.5, 0.6, 0.7],
            "timestamp": pd.to_datetime([
                "2024-01-01 12:00",
                "2024-01-01 13:00",
                "2024-01-01 14:00",
            ]).tz_localize("UTC"),
        })

        result = aggregate_trades_by_market(df)

        assert len(result) == 2

        m1_row = result[result["market_id"] == "0xm1"].iloc[0]
        assert m1_row["trade_count"] == 2
        assert m1_row["total_volume"] == 150.0
        assert m1_row["avg_price"] == 0.55

        m2_row = result[result["market_id"] == "0xm2"].iloc[0]
        assert m2_row["trade_count"] == 1
        assert m2_row["total_volume"] == 200.0


class TestFilterTrades:
    """Tests for filter_trades function."""

    def test_empty_dataframe(self):
        """Empty DataFrame should return empty."""
        df = pd.DataFrame(columns=["transaction_hash", "timestamp", "maker", "side", "size", "market_id"])
        result = filter_trades(df, start=datetime.now(timezone.utc))
        assert result.empty

    def test_filter_by_time_range(self):
        """Should filter by start and end timestamps."""
        df = pd.DataFrame({
            "transaction_hash": ["0x1", "0x2", "0x3"],
            "timestamp": pd.to_datetime([
                "2024-01-01",
                "2024-01-15",
                "2024-02-01",
            ]).tz_localize("UTC"),
            "maker": ["0xa", "0xa", "0xa"],
            "side": ["buy", "buy", "buy"],
            "size": [100, 100, 100],
            "market_id": ["0xm", "0xm", "0xm"],
        })

        result = filter_trades(
            df,
            start=datetime(2024, 1, 10, tzinfo=timezone.utc),
            end=datetime(2024, 1, 31, tzinfo=timezone.utc),
        )

        assert len(result) == 1
        assert result.iloc[0]["transaction_hash"] == "0x2"

    def test_filter_by_makers(self):
        """Should filter by maker addresses."""
        df = pd.DataFrame({
            "transaction_hash": ["0x1", "0x2", "0x3"],
            "timestamp": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-01"]).tz_localize("UTC"),
            "maker": ["0xa", "0xb", "0xc"],
            "side": ["buy", "buy", "buy"],
            "size": [100, 100, 100],
            "market_id": ["0xm", "0xm", "0xm"],
        })

        result = filter_trades(df, makers=["0xa", "0xc"])

        assert len(result) == 2
        assert set(result["maker"].values) == {"0xa", "0xc"}

    def test_filter_by_side(self):
        """Should filter by side."""
        df = pd.DataFrame({
            "transaction_hash": ["0x1", "0x2", "0x3", "0x4"],
            "timestamp": pd.to_datetime(["2024-01-01"] * 4).tz_localize("UTC"),
            "maker": ["0xa"] * 4,
            "side": ["buy", "sell", "buy", "sell"],
            "size": [100, 100, 100, 100],
            "market_id": ["0xm"] * 4,
        })

        result = filter_trades(df, sides=["buy"])

        assert len(result) == 2
        assert all(result["side"] == "buy")

    def test_filter_by_min_size(self):
        """Should filter by minimum size."""
        df = pd.DataFrame({
            "transaction_hash": ["0x1", "0x2", "0x3"],
            "timestamp": pd.to_datetime(["2024-01-01"] * 3).tz_localize("UTC"),
            "maker": ["0xa"] * 3,
            "side": ["buy"] * 3,
            "size": [50, 100, 150],
            "market_id": ["0xm"] * 3,
        })

        result = filter_trades(df, min_size=100)

        assert len(result) == 2
        assert all(result["size"] >= 100)


class TestComputeTradeStatistics:
    """Tests for compute_trade_statistics function."""

    def test_empty_dataframe(self):
        """Empty DataFrame should return zero statistics."""
        df = pd.DataFrame(columns=["transaction_hash", "size", "maker", "side", "market_id", "price", "timestamp"])
        stats = compute_trade_statistics(df)

        assert stats["total_trades"] == 0
        assert stats["total_volume"] == 0.0
        assert stats["unique_makers"] == 0
        assert stats["date_range"] is None

    def test_computes_correct_statistics(self):
        """Should compute correct summary statistics."""
        df = pd.DataFrame({
            "transaction_hash": ["0x1", "0x2", "0x3", "0x4"],
            "size": [100.0, 200.0, 150.0, 50.0],
            "maker": ["0xa", "0xa", "0xb", "0xc"],
            "side": ["buy", "sell", "buy", "sell"],
            "market_id": ["0xm1", "0xm1", "0xm2", "0xm3"],
            "price": [0.5, 0.6, 0.7, 0.4],
            "timestamp": pd.to_datetime([
                "2024-01-01 12:00",
                "2024-01-01 13:00",
                "2024-01-02 10:00",
                "2024-01-03 14:00",
            ]).tz_localize("UTC"),
        })

        stats = compute_trade_statistics(df)

        assert stats["total_trades"] == 4
        assert stats["total_volume"] == 500.0
        assert stats["unique_makers"] == 3
        assert stats["unique_markets"] == 3
        assert stats["buy_count"] == 2
        assert stats["sell_count"] == 2
        assert stats["avg_trade_size"] == 125.0
        assert stats["date_range"][0] < stats["date_range"][1]


class TestMergeTradeDataframes:
    """Tests for merge_trade_dataframes function."""

    def test_empty_list_returns_empty(self):
        """Empty list should return empty DataFrame."""
        result = merge_trade_dataframes([])
        assert result.empty

    def test_merge_single_dataframe(self):
        """Single DataFrame should return unchanged."""
        df = pd.DataFrame({
            "transaction_hash": ["0x1"],
            "timestamp": pd.to_datetime(["2024-01-01"]).tz_localize("UTC"),
            "price": [0.5],
        })

        result = merge_trade_dataframes([df])
        assert len(result) == 1

    def test_merge_multiple_dataframes(self):
        """Should merge multiple DataFrames."""
        df1 = pd.DataFrame({
            "transaction_hash": ["0x1", "0x2"],
            "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"]).tz_localize("UTC"),
            "price": [0.5, 0.6],
        })

        df2 = pd.DataFrame({
            "transaction_hash": ["0x3", "0x4"],
            "timestamp": pd.to_datetime(["2024-01-03", "2024-01-04"]).tz_localize("UTC"),
            "price": [0.7, 0.8],
        })

        result = merge_trade_dataframes([df1, df2])

        assert len(result) == 4

    def test_merge_removes_duplicates(self):
        """Should remove duplicates when remove_duplicates=True."""
        df1 = pd.DataFrame({
            "transaction_hash": ["0x1", "0x2"],
            "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"]).tz_localize("UTC"),
            "price": [0.5, 0.6],
        })

        df2 = pd.DataFrame({
            "transaction_hash": ["0x2", "0x3"],
            "timestamp": pd.to_datetime(["2024-01-02", "2024-01-03"]).tz_localize("UTC"),
            "price": [0.6, 0.7],
        })

        result = merge_trade_dataframes([df1, df2], remove_duplicates=True)

        assert len(result) == 3  # 0x2 duplicate removed

    def test_merge_sorts_by_timestamp(self):
        """Should sort result by timestamp."""
        df1 = pd.DataFrame({
            "transaction_hash": ["0x2", "0x1"],
            "timestamp": pd.to_datetime(["2024-01-02", "2024-01-01"]).tz_localize("UTC"),
            "price": [0.6, 0.5],
        })

        df2 = pd.DataFrame({
            "transaction_hash": ["0x4", "0x3"],
            "timestamp": pd.to_datetime(["2024-01-04", "2024-01-03"]).tz_localize("UTC"),
            "price": [0.8, 0.7],
        })

        result = merge_trade_dataframes([df1, df2])

        # Should be sorted by timestamp
        assert result.iloc[0]["transaction_hash"] == "0x1"
        assert result.iloc[-1]["transaction_hash"] == "0x4"

    def test_filters_empty_dataframes(self):
        """Should filter out empty DataFrames."""
        df1 = pd.DataFrame({
            "transaction_hash": ["0x1"],
            "timestamp": pd.to_datetime(["2024-01-01"]).tz_localize("UTC"),
            "price": [0.5],
        })

        df2 = pd.DataFrame(columns=["transaction_hash", "timestamp", "price"])

        result = merge_trade_dataframes([df1, df2])

        assert len(result) == 1
