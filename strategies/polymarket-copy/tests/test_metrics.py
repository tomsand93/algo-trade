"""
Tests for backtest metrics calculation.
"""

from datetime import datetime, timedelta, timezone

import pytest

from pmirror.domain.engine import BacktestResult
from pmirror.domain.metrics import calculate_metrics
from pmirror.domain.models import ExecutedTrade


class TestCalculateMetrics:
    """Tests for calculate_metrics function."""

    def test_basic_metrics(self):
        """Should calculate basic metrics from backtest result."""
        result = BacktestResult(
            initial_cash=10000.0,
            final_cash=11200.0,
            total_return=0.12,
            executed_trades=[
                ExecutedTrade(
                    timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                    market_id="0x123",
                    side="buy",
                    price=0.65,
                    size=100.0,
                    shares=154.0,
                    slippage_bps=10.0,
                    fee=1.0,
                )
            ],
            skipped_trades=2,
            timestamps=[datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)],
        )

        metrics = calculate_metrics(result, target_return=0.15)

        assert metrics.total_return == 0.12
        assert metrics.final_equity == 11200.0
        assert metrics.total_trades == 1
        assert metrics.skipped_trades == 2
        assert metrics.skipped_rate == 2 / 3
        assert metrics.target_return == 0.15

    def test_empty_backtest(self):
        """Should handle backtest with no trades."""
        result = BacktestResult(
            initial_cash=10000.0,
            final_cash=10000.0,
            total_return=0.0,
            executed_trades=[],
            skipped_trades=0,
            timestamps=[],
        )

        metrics = calculate_metrics(result)

        assert metrics.total_return == 0.0
        assert metrics.total_trades == 0
        assert metrics.skipped_trades == 0
        assert metrics.skipped_rate == 0.0

    def test_sharpe_ratio_calculation(self):
        """Should calculate Sharpe ratio from returns."""
        trades = [
            ExecutedTrade(
                timestamp=datetime(2024, 1, i + 1, 12, 0, 0, tzinfo=timezone.utc),
                market_id="0x123",
                side="buy" if i % 2 == 0 else "sell",
                price=0.5 + (i * 0.01),
                size=100.0,
                shares=200.0,
                slippage_bps=10.0,
                fee=0.0,
            )
            for i in range(10)
        ]

        result = BacktestResult(
            initial_cash=10000.0,
            final_cash=10500.0,
            total_return=0.05,
            executed_trades=trades,
            skipped_trades=0,
            timestamps=[t.timestamp for t in trades],
        )

        metrics = calculate_metrics(result)
        assert isinstance(metrics.sharpe_ratio, float)

    def test_max_drawdown(self):
        """Should calculate maximum drawdown."""
        trades = [
            ExecutedTrade(
                timestamp=datetime(2024, 1, i + 1, 12, 0, 0, tzinfo=timezone.utc),
                market_id="0x123",
                side="buy",
                price=0.50,
                size=100.0,
                shares=200.0,
                slippage_bps=0.0,
                fee=0.0,
            )
            for i in range(5)
        ]

        result = BacktestResult(
            initial_cash=10000.0,
            final_cash=9500.0,
            total_return=-0.05,
            executed_trades=trades,
            skipped_trades=0,
            timestamps=[t.timestamp for t in trades],
        )

        metrics = calculate_metrics(result)
        assert 0 <= metrics.max_drawdown <= 1
        assert metrics.peak_equity >= metrics.final_equity

    def test_total_fees(self):
        """Should sum up all fees paid."""
        result = BacktestResult(
            initial_cash=10000.0,
            final_cash=9900.0,
            total_return=-0.01,
            executed_trades=[
                ExecutedTrade(
                    timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                    market_id="0x123",
                    side="buy",
                    price=0.50,
                    size=100.0,
                    shares=200.0,
                    slippage_bps=0.0,
                    fee=5.0,
                ),
                ExecutedTrade(
                    timestamp=datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc),
                    market_id="0x123",
                    side="sell",
                    price=0.50,
                    size=100.0,
                    shares=200.0,
                    slippage_bps=0.0,
                    fee=5.0,
                ),
            ],
            skipped_trades=0,
            timestamps=[
                datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc),
            ],
        )

        metrics = calculate_metrics(result)
        assert metrics.total_fees == 10.0

    def test_skipped_rate_with_no_trades(self):
        """Should handle skipped rate when no trades at all."""
        result = BacktestResult(
            initial_cash=10000.0,
            final_cash=10000.0,
            total_return=0.0,
            executed_trades=[],
            skipped_trades=0,
            timestamps=[],
        )

        metrics = calculate_metrics(result)
        assert metrics.skipped_rate == 0.0

    def test_all_trades_skipped(self):
        """Should handle case where all trades were skipped."""
        result = BacktestResult(
            initial_cash=10000.0,
            final_cash=10000.0,
            total_return=0.0,
            executed_trades=[],
            skipped_trades=10,
            timestamps=[],
        )

        metrics = calculate_metrics(result)
        assert metrics.total_trades == 0
        assert metrics.skipped_trades == 10
        assert metrics.skipped_rate == 1.0
