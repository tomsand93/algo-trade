"""
Tests for parquet storage operations.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import pytest
import pytz

from pmirror.domain import Trade
from pmirror.data.storage import (
    TradeStorage,
    save_markets,
    load_markets,
)


class TestTradeStorage:
    """Tests for TradeStorage class."""

    @pytest.fixture
    def storage(self, tmp_path):
        """Create a TradeStorage instance with temp directory."""
        from pmirror.config import Settings, DataConfig

        settings = Settings(
            data=DataConfig(
                data_root=tmp_path,
                clean_data_dir=tmp_path / "clean",
            )
        )
        return TradeStorage(settings=settings)

    @pytest.fixture
    def sample_df(self):
        """Create a sample trade DataFrame."""
        return pd.DataFrame({
            "transaction_hash": ["0x1", "0x2", "0x3"],
            "timestamp": pd.to_datetime([
                "2024-01-01 12:00",
                "2024-01-02 13:00",
                "2024-01-03 14:00",
            ]).tz_localize("UTC"),
            "maker": ["0xa", "0xb", "0xc"],
            "taker": [None, None, None],
            "side": ["buy", "sell", "buy"],
            "outcome": ["yes", "no", "yes"],
            "price": [0.5, 0.6, 0.7],
            "size": [100.0, 200.0, 150.0],
            "shares": [200.0, 333.33, 214.29],
            "fee": [None, None, None],
            "market_id": ["0xm1", "0xm1", "0xm2"],
        })

    def test_save_trades_creates_file(self, storage, sample_df):
        """Should create parquet file when saving trades."""
        path = storage.save_trades(sample_df)

        assert path.exists()
        assert path.suffix == ".parquet"

    def test_save_trades_empty_dataframe_raises(self, storage):
        """Should raise ValueError when saving empty DataFrame."""
        empty_df = pd.DataFrame(columns=["transaction_hash", "timestamp"])

        with pytest.raises(ValueError, match="empty"):
            storage.save_trades(empty_df)

    def test_save_trades_missing_columns_raises(self, storage):
        """Should raise ValueError when required columns are missing."""
        bad_df = pd.DataFrame({"col1": [1, 2], "col2": [3, 4]})

        with pytest.raises(ValueError, match="missing required columns"):
            storage.save_trades(bad_df)

    def test_load_trades_returns_data(self, storage, sample_df):
        """Should load trades from parquet file."""
        storage.save_trades(sample_df)
        loaded = storage.load_trades()

        assert len(loaded) == 3
        assert list(loaded["transaction_hash"]) == ["0x1", "0x2", "0x3"]

    def test_load_trades_nonexistent_returns_empty(self, storage):
        """Should return empty DataFrame when file doesn't exist."""
        result = storage.load_trades()

        assert result.empty
        assert "transaction_hash" in result.columns

    def test_append_trades_adds_to_existing(self, storage, sample_df):
        """Should append new trades to existing file."""
        # Save initial trades
        storage.save_trades(sample_df.iloc[:2])

        # Append more
        new_df = sample_df.iloc[2:]
        storage.append_trades(new_df)

        # Load and verify
        loaded = storage.load_trades()
        assert len(loaded) == 3

    def test_append_trades_deduplicates(self, storage, sample_df):
        """Should remove duplicates when appending."""
        # Save initial trades
        storage.save_trades(sample_df)

        # Try to append duplicate
        storage.append_trades(sample_df, deduplicate=True)

        # Should still have 3 unique trades
        loaded = storage.load_trades()
        assert len(loaded) == 3

    def test_save_trades_by_date_partitions(self, storage, sample_df):
        """Should partition trades by date."""
        paths = storage.save_trades_by_date(sample_df)

        assert len(paths) == 3  # 3 different dates
        for date_str, path in paths.items():
            assert path.exists()
            assert path.parent.name in ["01", "02", "03"]  # Month directories

    def test_load_trades_by_date_filters(self, storage, sample_df):
        """Should load trades for specific date range."""
        storage.save_trades_by_date(sample_df)

        # Load only first 2 days
        result = storage.load_trades_by_date(
            start_date="2024-01-01",
            end_date="2024-01-02"
        )

        assert len(result) == 2

    def test_save_wallet_trades(self, storage, sample_df):
        """Should save trades for specific wallet."""
        path = storage.save_wallet_trades(sample_df, "0xabc123")

        assert path.exists()
        assert "0xabc123.parquet" in str(path)

    def test_load_wallet_trades(self, storage, sample_df):
        """Should load trades for specific wallet."""
        storage.save_wallet_trades(sample_df, "0xabc123")
        loaded = storage.load_wallet_trades("0xabc123")

        assert len(loaded) == 3

    def test_list_wallets(self, storage, sample_df):
        """Should list all wallets with saved data."""
        storage.save_wallet_trades(sample_df, "0xaaa")
        storage.save_wallet_trades(sample_df, "0xbbb")
        storage.save_wallet_trades(sample_df, "0xccc")

        wallets = storage.list_wallets()

        assert sorted(wallets) == ["0xaaa", "0xbbb", "0xccc"]

    def test_get_storage_info(self, storage, sample_df):
        """Should return storage information."""
        path = storage.save_trades(sample_df)
        info = storage.get_storage_info(path)

        assert info["exists"] is True
        assert info["trade_count"] == 3
        assert info["size_bytes"] > 0
        assert info["date_range"] is not None

    def test_get_storage_info_nonexistent(self, storage):
        """Should handle non-existent files."""
        info = storage.get_storage_info("nonexistent.parquet")

        assert info["exists"] is False
        assert info["trade_count"] == 0

    def test_delete_file(self, storage, sample_df):
        """Should delete parquet file."""
        path = storage.save_trades(sample_df)

        result = storage.delete_file(path)

        assert result is True
        assert not path.exists()

    def test_delete_file_nonexistent(self, storage):
        """Should return False when deleting non-existent file."""
        result = storage.delete_file("nonexistent.parquet")
        assert result is False

    def test_clear_all(self, storage, sample_df):
        """Should delete all parquet files."""
        storage.save_trades_by_date(sample_df)
        storage.save_wallet_trades(sample_df, "0xwallet")

        count = storage.clear_all()

        assert count >= 4  # At least the files we created

    def test_timezone_preservation(self, storage):
        """Should preserve timezone information."""
        df = pd.DataFrame({
            "transaction_hash": ["0x1"],
            "timestamp": pd.to_datetime(["2024-01-01"]).tz_localize("UTC"),
            "maker": ["0xa"],
            "side": ["buy"],
            "outcome": ["yes"],
            "price": [0.5],
            "size": [100],
            "market_id": ["0xm"],
        })

        storage.save_trades(df)
        loaded = storage.load_trades()

        # Timestamp should still be timezone-aware
        assert loaded["timestamp"].dt.tz is not None


class TestMarketStorage:
    """Tests for market metadata storage."""

    def test_save_and_load_markets(self, tmp_path):
        """Should save and load market metadata."""
        markets = [
            {
                "condition_id": "0x123",
                "question": "Will it rain?",
                "outcomes": ["yes", "no"],
                "end_time": datetime(2024, 12, 31, tzinfo=timezone.utc),
                "resolution": None,
            },
            {
                "condition_id": "0x456",
                "question": "Who will win?",
                "outcomes": ["A", "B", "C"],
                "end_time": datetime(2024, 6, 30, tzinfo=timezone.utc),
                "resolution": "A",
            },
        ]

        from pmirror.config import Settings, DataConfig
        settings = Settings(
            data=DataConfig(clean_data_dir=tmp_path)
        )

        path = save_markets(markets, settings=settings)
        loaded = load_markets(settings=settings)

        assert len(loaded) == 2
        assert loaded.iloc[0]["condition_id"] == "0x123"
        assert loaded.iloc[1]["resolution"] == "A"

    def test_load_markets_nonexistent_returns_empty(self, tmp_path):
        """Should return empty DataFrame when file doesn't exist."""
        from pmirror.config import Settings, DataConfig
        settings = Settings(
            data=DataConfig(clean_data_dir=tmp_path)
        )

        loaded = load_markets(settings=settings)

        assert loaded.empty
        assert "condition_id" in loaded.columns
