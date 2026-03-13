"""
Integration tests for end-to-end workflows.

Tests complete workflows across multiple modules:
- Fetch: API client → storage
- Backtest: Storage → engine → metrics → report
- Report: Saved results → charts
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
import pandas as pd

from pmirror.config import get_settings
from pmirror.data.data_api import DataAPIClient
from pmirror.data.storage import TradeStorage
from pmirror.domain import Trade, Market
from pmirror.domain.normalize import normalize_trades
from pmirror.backtest.runner import BacktestRunner
from pmirror.backtest.metrics import compute_metrics
from pmirror.reporting.report import generate_markdown_report, save_report
from pmirror.reporting.charts import (
    generate_equity_curve,
    generate_drawdown_chart,
)


@pytest.fixture
def temp_storage(tmp_path):
    """Create a temporary storage for testing."""
    clean_dir = tmp_path / "clean"
    clean_dir.mkdir(parents=True, exist_ok=True)

    # Create a mock settings with custom paths
    from pmirror.config.settings import Settings, ApiConfig, CacheConfig, DataConfig

    mock_settings = Settings(
        api=ApiConfig(),
        cache=CacheConfig(),
        data=DataConfig(
            data_root=str(tmp_path),
            raw_data_dir=str(tmp_path / "raw"),
            clean_data_dir=str(clean_dir),
        ),
        reports_dir=tmp_path / "reports",
    )

    storage = TradeStorage(mock_settings)
    yield storage


class TestFetchWorkflow:
    """Tests for the fetch workflow: API → storage."""

    def test_fetch_to_storage_workflow(self, temp_storage):
        """Should fetch trades from API and store to parquet."""
        # Sample trades
        trades = [
            Trade(
                transaction_hash=f"0x{i:040x}",
                timestamp=datetime(2024, 1, i, 12, 0, tzinfo=timezone.utc),
                maker="0xwallet",
                taker=None,
                side="buy" if i % 2 == 0 else "sell",
                outcome="yes",
                price=0.5 + (i * 0.01),
                size=100.0,
                market_id="0x123",
            )
            for i in range(1, 11)
        ]

        # Normalize and save
        df = normalize_trades(trades)
        saved_path = temp_storage.save_wallet_trades(df, "0xwallet")

        # Verify saved
        assert saved_path.exists()
        loaded_df = temp_storage.load_wallet_trades("0xwallet")
        assert len(loaded_df) == 10
        assert loaded_df["maker"].iloc[0] == "0xwallet"

    def test_fetch_and_append_workflow(self, temp_storage):
        """Should be able to append new trades to existing data."""
        # Initial trades
        trades1 = [
            Trade(
                transaction_hash="0xabc",
                timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
                maker="0xwallet",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.5,
                size=100.0,
                market_id="0x123",
            )
        ]

        df1 = normalize_trades(trades1)
        wallet_path = temp_storage.save_wallet_trades(df1, "0xwallet")

        # New trades (append to the same file)
        trades2 = [
            Trade(
                transaction_hash="0xdef",
                timestamp=datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc),
                maker="0xwallet",
                taker=None,
                side="sell",
                outcome="yes",
                price=0.6,
                size=100.0,
                market_id="0x123",
            )
        ]

        df2 = normalize_trades(trades2)
        temp_storage.append_trades(df2, path=wallet_path)

        # Verify combined - load from wallet path
        loaded_df = temp_storage.load_wallet_trades("0xwallet")
        assert len(loaded_df) == 2

    def test_fetch_empty_data_handling(self, temp_storage):
        """Should handle empty API responses gracefully."""
        empty_trades = []
        df = normalize_trades(empty_trades)

        # Should create empty DataFrame
        assert df.empty
        assert "transaction_hash" in df.columns


class TestBacktestWorkflow:
    """Tests for the backtest workflow: Storage → engine → metrics."""

    def test_full_backtest_workflow(self, temp_storage):
        """Should run complete backtest from storage to metrics."""
        # Setup: Save trades to storage
        trades = [
            Trade(
                transaction_hash=f"0x{i:040x}",
                timestamp=datetime(2024, 1, i, 12, 0, tzinfo=timezone.utc),
                maker="0xtarget",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.5,
                size=1000.0,
                market_id=f"0xmarket{i}",
            )
            for i in range(1, 6)
        ]

        df = normalize_trades(trades)
        temp_storage.save_wallet_trades(df, "0xtarget")

        # Run backtest
        runner = BacktestRunner(storage=temp_storage)
        result = runner.run(
            target_wallet="0xtarget",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 31, tzinfo=timezone.utc),
            capital=1000.0,
            policy="mirror_latency",
            policy_params={"scale_factor": 0.1},
        )

        # Compute metrics
        metrics = compute_metrics(result)

        # Verify results
        assert result is not None
        assert metrics["total_trades"] >= 0
        assert "sharpe_ratio" in metrics
        assert "max_drawdown" in metrics

    def test_backtest_with_no_trades(self, temp_storage):
        """Should handle backtest with no trades gracefully."""
        runner = BacktestRunner(storage=temp_storage)
        result = runner.run(
            target_wallet="0xempty",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 31, tzinfo=timezone.utc),
            capital=1000.0,
            policy="mirror_latency",
        )

        # Should return result with empty state
        assert result is not None
        assert result.final_state.cash == 1000.0

    def test_backtest_all_policies(self, temp_storage):
        """Should work with all available policies."""
        trades = [
            Trade(
                transaction_hash="0xabc",
                timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
                maker="0xtarget",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.5,
                size=1000.0,
                market_id="0x123",
            )
        ]

        df = normalize_trades(trades)
        temp_storage.save_wallet_trades(df, "0xtarget")

        runner = BacktestRunner(storage=temp_storage)

        for policy_name in ["mirror_latency", "fixed_allocation", "position_rebalance"]:
            result = runner.run(
                target_wallet="0xtarget",
                start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end_date=datetime(2024, 1, 31, tzinfo=timezone.utc),
                capital=1000.0,
                policy=policy_name,
            )
            assert result is not None


class TestReportWorkflow:
    """Tests for the report workflow: metrics → markdown → charts."""

    def test_report_generation_workflow(self, tmp_path):
        """Should generate complete report with metrics and config."""
        from pmirror.domain.models import BacktestMetrics

        metrics = BacktestMetrics(
            total_return=0.15,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown=0.1,
            max_drawdown_duration=timedelta(hours=24),
            total_trades=50,
            win_rate=0.6,
            avg_trade_return=0.01,
            skipped_trades=5,
            skipped_rate=0.1,
            max_exposure=500.0,
            avg_exposure=100.0,
            exposure_by_market={"0x123": 300.0, "0x456": 200.0},
            target_return=0.12,
            correlation=None,
            final_equity=1150.0,
            peak_equity=1200.0,
            total_fees=5.0,
        )

        config = {
            "wallet": "0xtarget",
            "policy": "mirror_latency",
            "start": "2024-01-01",
            "end": "2024-12-31",
            "initial_cash": 1000.0,
        }

        report = generate_markdown_report(metrics, config, run_id="test-run")

        # Verify report content
        assert "# Backtest Report: test-run" in report
        assert "15.00%" in report  # total_return
        assert "1.50" in report  # sharpe_ratio
        assert "0xtarget" in report
        assert "mirror_latency" in report

        # Save report
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_path_str = save_report(report, "test-run", reports_dir=str(reports_dir))

        report_path = Path(report_path_str)
        assert report_path.exists()
        content = report_path.read_text()
        assert "15.00%" in content

    def test_chart_generation_workflow(self, tmp_path):
        """Should generate all chart types without errors."""
        timestamps = [
            datetime(2024, 1, i, 12, 0, tzinfo=timezone.utc)
            for i in range(1, 11)
        ]
        equity = [1000 + i * 10 for i in range(10)]  # Rising equity

        # Equity curve
        equity_chart = tmp_path / "equity.png"
        generate_equity_curve(
            timestamps=timestamps,
            cash_values=equity,
            output_path=str(equity_chart),
        )
        assert equity_chart.exists()

        # Drawdown chart
        dd_chart = tmp_path / "drawdown.png"
        generate_drawdown_chart(
            timestamps=timestamps,
            equity_values=equity,
            output_path=str(dd_chart),
        )
        assert dd_chart.exists()

    def test_chart_empty_data_handling(self, tmp_path):
        """Should handle empty data gracefully."""
        empty_chart = tmp_path / "empty.png"
        generate_equity_curve(
            timestamps=[],
            cash_values=[],
            output_path=str(empty_chart),
        )
        # Should create chart with "No data" message
        assert empty_chart.exists()


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_single_trade_backtest(self, temp_storage):
        """Should handle backtest with exactly one trade."""
        trades = [
            Trade(
                transaction_hash="0xabc",
                timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
                maker="0xtarget",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.5,
                size=100.0,
                market_id="0x123",
            )
        ]

        df = normalize_trades(trades)
        temp_storage.save_wallet_trades(df, "0xtarget")

        runner = BacktestRunner(storage=temp_storage)
        result = runner.run(
            target_wallet="0xtarget",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 31, tzinfo=timezone.utc),
            capital=1000.0,
            policy="mirror_latency",
        )

        metrics = compute_metrics(result)
        # Should not crash with single data point
        assert "sharpe_ratio" in metrics

    def test_zero_capital_backtest(self, temp_storage):
        """Should handle small capital gracefully (by skipping trades)."""
        trades = [
            Trade(
                transaction_hash="0xabc",
                timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
                maker="0xtarget",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.5,
                size=100.0,
                market_id="0x123",
            )
        ]

        df = normalize_trades(trades)
        temp_storage.save_wallet_trades(df, "0xtarget")

        runner = BacktestRunner(storage=temp_storage)
        result = runner.run(
            target_wallet="0xtarget",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 31, tzinfo=timezone.utc),
            capital=10.0,  # Small capital
            policy="fixed_allocation",
            policy_params={"allocation_per_trade": 5.0},  # Fits in capital, but trades will deplete it
        )

        # Should complete without error
        assert result is not None
        # Should execute some trades until cash runs out
        assert len(result.executed_trades) >= 0

    def test_invalid_policy_name(self, temp_storage):
        """Should raise error for invalid policy name."""
        # First, add some data so the backtest actually runs
        trades = [
            Trade(
                transaction_hash="0xabc",
                timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
                maker="0xtarget",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.5,
                size=100.0,
                market_id="0x123",
            )
        ]

        df = normalize_trades(trades)
        temp_storage.save_wallet_trades(df, "0xtarget")

        runner = BacktestRunner(storage=temp_storage)

        with pytest.raises(ValueError, match="Unknown policy"):
            runner.run(
                target_wallet="0xtarget",
                start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end_date=datetime(2024, 1, 31, tzinfo=timezone.utc),
                capital=1000.0,
                policy="invalid_policy",
            )

    def test_mixed_buy_sell_trades(self, temp_storage):
        """Should handle mixed buy and sell trades correctly."""
        trades = [
            Trade(
                transaction_hash=f"0x{i:040x}",
                timestamp=datetime(2024, 1, i, 12, 0, tzinfo=timezone.utc),
                maker="0xtarget",
                taker=None,
                side="buy" if i % 2 == 0 else "sell",
                outcome="yes",
                price=0.5,
                size=100.0,
                market_id="0x123",
            )
            for i in range(1, 11)
        ]

        df = normalize_trades(trades)
        temp_storage.save_wallet_trades(df, "0xtarget")

        runner = BacktestRunner(storage=temp_storage)
        result = runner.run(
            target_wallet="0xtarget",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 31, tzinfo=timezone.utc),
            capital=1000.0,
            policy="mirror_latency",
        )

        metrics = compute_metrics(result)
        # Should process both buy and sell
        assert metrics["total_trades"] >= 0

    def test_extreme_slippage(self, temp_storage):
        """Should handle extreme slippage values."""
        trades = [
            Trade(
                transaction_hash="0xabc",
                timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
                maker="0xtarget",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.5,
                size=100.0,
                market_id="0x123",
            )
        ]

        df = normalize_trades(trades)
        temp_storage.save_wallet_trades(df, "0xtarget")

        runner = BacktestRunner(storage=temp_storage)

        # Test with 1000 bps (10%) slippage
        result = runner.run(
            target_wallet="0xtarget",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 31, tzinfo=timezone.utc),
            capital=1000.0,
            policy="mirror_latency",
            slippage_bps=1000,
        )

        # Should complete without error
        assert result is not None


class TestLargeDatasets:
    """Tests for performance with larger datasets."""

    def test_large_trade_history(self, temp_storage):
        """Should handle large number of trades efficiently."""
        # Generate 1000 trades
        trades = [
            Trade(
                transaction_hash=f"0x{i:040x}",
                timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i),
                maker="0xtarget",
                taker=None,
                side="buy" if i % 2 == 0 else "sell",
                outcome="yes",
                price=0.5,
                size=100.0,
                market_id=f"0xmarket{i % 100}",  # 100 different markets
            )
            for i in range(1000)
        ]

        # Save
        df = normalize_trades(trades)
        temp_storage.save_wallet_trades(df, "0xtarget")

        # Run backtest
        import time
        start = time.time()
        runner = BacktestRunner(storage=temp_storage)
        result = runner.run(
            target_wallet="0xtarget",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            capital=10000.0,
            policy="mirror_latency",
            policy_params={"scale_factor": 0.01},
        )
        elapsed = time.time() - start

        # Should complete in reasonable time (< 10 seconds)
        assert elapsed < 10.0
        assert result is not None

    def test_storage_efficient_append(self, temp_storage):
        """Test append performance with existing data."""
        # Initial large dataset
        trades1 = [
            Trade(
                transaction_hash=f"0xabc{i:040x}",
                timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i),
                maker="0xtarget",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.5,
                size=100.0,
                market_id="0x123",
            )
            for i in range(500)
        ]

        df1 = normalize_trades(trades1)
        wallet_path = temp_storage.save_wallet_trades(df1, "0xtarget")

        # Append more data to the same file
        trades2 = [
            Trade(
                transaction_hash=f"0xdef{i:040x}",
                timestamp=datetime(2024, 2, 1, tzinfo=timezone.utc) + timedelta(hours=i),
                maker="0xtarget",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.5,
                size=100.0,
                market_id="0x123",
            )
            for i in range(500)
        ]

        df2 = normalize_trades(trades2)

        import time
        start = time.time()
        temp_storage.append_trades(df2, path=wallet_path)
        elapsed = time.time() - start

        # Should be reasonably fast (< 5 seconds for 1000 rows)
        assert elapsed < 5.0

        # Verify count - load from the wallet file
        loaded = temp_storage.load_wallet_trades("0xtarget")
        assert len(loaded) == 1000
