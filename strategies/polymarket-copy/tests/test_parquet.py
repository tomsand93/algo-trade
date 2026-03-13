"""
Tests for parquet storage operations.
"""

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from pmirror.domain import Trade
from pmirror.domain.normalize import (
    save_trades_parquet,
    load_trades_parquet,
    save_dataframe_parquet,
    load_dataframe_parquet,
)


class TestSaveLoadTradesParquet:
    """Tests for save_trades_parquet and load_trades_parquet functions."""

    def test_save_load_single_trade(self, tmp_path):
        """Should save and load a single trade correctly."""
        trades = [
            Trade(
                transaction_hash="0xabc",
                timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                maker="0xwallet",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.65,
                size=100.0,
                market_id="0x123",
            )
        ]
        path = tmp_path / "trades.parquet"
        save_trades_parquet(trades, str(path))

        assert path.exists()

        loaded = load_trades_parquet(str(path))
        assert len(loaded) == 1
        assert loaded[0].transaction_hash == "0xabc"
        assert loaded[0].maker == "0xwallet"
        assert loaded[0].side == "buy"
        assert loaded[0].price == 0.65
        assert loaded[0].size == 100.0

    def test_save_load_multiple_trades(self, tmp_path):
        """Should save and load multiple trades correctly."""
        trades = [
            Trade(
                transaction_hash=f"0x{i}",
                timestamp=datetime(2024, 1, i, 12, 0, 0, tzinfo=timezone.utc),
                maker="0xwallet",
                taker=None,
                side="buy" if i % 2 == 0 else "sell",
                outcome="yes",
                price=0.5 + (i * 0.05),
                size=100.0,
                market_id="0x123",
            )
            for i in range(1, 6)
        ]
        path = tmp_path / "trades.parquet"
        save_trades_parquet(trades, str(path))

        loaded = load_trades_parquet(str(path))
        assert len(loaded) == 5
        assert {t.transaction_hash for t in loaded} == {"0x1", "0x2", "0x3", "0x4", "0x5"}

    def test_save_empty_list(self, tmp_path):
        """Should handle empty trade list gracefully."""
        path = tmp_path / "empty.parquet"
        save_trades_parquet([], str(path))

        assert path.exists()

        loaded = load_trades_parquet(str(path))
        assert len(loaded) == 0

    def test_load_creates_directory_if_needed(self, tmp_path):
        """Should create parent directories if they don't exist."""
        trades = [
            Trade(
                transaction_hash="0xabc",
                timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
                maker="0xwallet",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.5,
                size=100.0,
                market_id="0x123",
            )
        ]
        nested_path = tmp_path / "subdir" / "trades.parquet"
        save_trades_parquet(trades, str(nested_path))

        assert nested_path.exists()

    def test_preserves_timestamp_timezone(self, tmp_path):
        """Should preserve timezone information in timestamps."""
        trades = [
            Trade(
                transaction_hash="0xtz",
                timestamp=datetime(2024, 6, 15, 14, 30, 0, tzinfo=timezone.utc),
                maker="0xwallet",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.75,
                size=50.0,
                market_id="0x123",
            )
        ]
        path = tmp_path / "tz.parquet"
        save_trades_parquet(trades, str(path))

        loaded = load_trades_parquet(str(path))
        assert loaded[0].timestamp.tzinfo is not None
        assert loaded[0].timestamp.hour == 14

    def test_load_nonexistent_file_raises(self, tmp_path):
        """Should raise error when loading non-existent file."""
        with pytest.raises(FileNotFoundError):
            load_trades_parquet(str(tmp_path / "nonexistent.parquet"))


class TestSaveLoadDataFrameParquet:
    """Tests for DataFrame-based parquet operations."""

    def test_save_load_dataframe(self, tmp_path):
        """Should save and load DataFrame correctly."""
        df = pd.DataFrame({
            "transaction_hash": ["0x1", "0x2"],
            "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"]).tz_localize("UTC"),
            "maker": ["0xa", "0xb"],
            "taker": [None, None],
            "side": ["buy", "sell"],
            "outcome": ["yes", "no"],
            "price": [0.5, 0.6],
            "size": [100.0, 200.0],
            "market_id": ["0xm1", "0xm2"],
            "shares": [200.0, 333.33],
            "fee": [None, None],
        })

        path = tmp_path / "dataframe.parquet"
        save_dataframe_parquet(df, str(path))

        loaded = load_dataframe_parquet(str(path))
        assert len(loaded) == 2
        assert list(loaded.columns) == list(df.columns)

    def test_save_load_empty_dataframe(self, tmp_path):
        """Should handle empty DataFrame."""
        df = pd.DataFrame(columns=[
            "transaction_hash", "timestamp", "maker", "taker",
            "side", "outcome", "price", "size", "market_id"
        ])

        path = tmp_path / "empty_df.parquet"
        save_dataframe_parquet(df, str(path))

        loaded = load_dataframe_parquet(str(path))
        assert len(loaded) == 0

    def test_append_mode(self, tmp_path):
        """Should append data to existing parquet file."""
        # Save initial data
        df1 = pd.DataFrame({
            "transaction_hash": ["0x1", "0x2"],
            "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"]).tz_localize("UTC"),
            "maker": ["0xa", "0xb"],
            "taker": [None, None],
            "side": ["buy", "sell"],
            "outcome": ["yes", "no"],
            "price": [0.5, 0.6],
            "size": [100.0, 200.0],
            "market_id": ["0xm1", "0xm2"],
        })

        path = tmp_path / "append.parquet"
        save_dataframe_parquet(df1, str(path))

        # Append more data
        df2 = pd.DataFrame({
            "transaction_hash": ["0x3"],
            "timestamp": pd.to_datetime(["2024-01-03"]).tz_localize("UTC"),
            "maker": ["0xc"],
            "taker": [None],
            "side": ["buy"],
            "outcome": ["yes"],
            "price": [0.7],
            "size": [150.0],
            "market_id": ["0xm3"],
        })

        save_dataframe_parquet(df2, str(path), mode="append")

        # Load and verify
        loaded = load_dataframe_parquet(str(path))
        assert len(loaded) == 3
        assert set(loaded["transaction_hash"].values) == {"0x1", "0x2", "0x3"}

    def test_overwrite_mode(self, tmp_path):
        """Should overwrite existing data when mode='overwrite'."""
        # Save initial data
        df1 = pd.DataFrame({
            "transaction_hash": ["0x1", "0x2"],
            "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"]).tz_localize("UTC"),
            "maker": ["0xa", "0xb"],
            "taker": [None, None],
            "side": ["buy", "sell"],
            "outcome": ["yes", "no"],
            "price": [0.5, 0.6],
            "size": [100.0, 200.0],
            "market_id": ["0xm1", "0xm2"],
        })

        path = tmp_path / "overwrite.parquet"
        save_dataframe_parquet(df1, str(path))

        # Overwrite with new data
        df2 = pd.DataFrame({
            "transaction_hash": ["0x3"],
            "timestamp": pd.to_datetime(["2024-01-03"]).tz_localize("UTC"),
            "maker": ["0xc"],
            "taker": [None],
            "side": ["buy"],
            "outcome": ["yes"],
            "price": [0.7],
            "size": [150.0],
            "market_id": ["0xm3"],
        })

        save_dataframe_parquet(df2, str(path), mode="overwrite")

        # Load and verify
        loaded = load_dataframe_parquet(str(path))
        assert len(loaded) == 1
        assert loaded.iloc[0]["transaction_hash"] == "0x3"
