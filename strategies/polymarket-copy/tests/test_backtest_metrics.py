"""
Tests for pmirror.backtest.metrics module.
"""

from datetime import datetime, timedelta, timezone

import pytest

from pmirror.backtest.engine import BacktestResult, BacktestConfig, BacktestState
from pmirror.backtest.metrics import compute_metrics, format_metrics
from pmirror.domain import ExecutedTrade, Position, Trade


# Create a test helper to make BacktestResult since it's a dataclass
def make_backtest_result(
    starting_cash: float,
    final_equity: float,
    trades: list[ExecutedTrade],
    skipped: list[Trade] | None = None,
    commission_rate: float = 0.0,
) -> BacktestResult:
    """Helper to create BacktestResult for testing."""
    total_return = (final_equity - starting_cash) / starting_cash if starting_cash > 0 else 0.0

    state = BacktestState(
        starting_cash=starting_cash,
        cash=final_equity,  # Simplified
        equity=final_equity,
        positions={},
        total_return=total_return,
    )

    config = BacktestConfig(
        target_wallet="0xtest",
        capital=starting_cash,
        policy=None,  # No policy needed for metrics computation
        commission_rate=commission_rate,
        slippage_bps=5,
    )

    return BacktestResult(
        final_state=state,
        executed_trades=trades,
        skipped_trades=skipped or [],
        config=config,
    )


class TestComputeMetrics:
    """Tests for compute_metrics function."""

    def test_basic_metrics_with_single_trade(self):
        """Should calculate basic metrics from backtest with one trade."""
        trade = ExecutedTrade(
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            market_id="0x123",
            side="buy",
            price=0.65,
            size=100.0,
            shares=154.0,
            slippage_bps=10.0,
            fee=1.0,
        )

        result = make_backtest_result(
            starting_cash=10000.0,
            final_equity=10000.0,
            trades=[trade],
        )

        metrics = compute_metrics(result)

        assert metrics["total_return"] == 0.0
        assert metrics["final_equity"] == 10000.0
        assert metrics["total_trades"] == 1
        assert metrics["skipped_trades"] == 0
        assert metrics["skip_rate"] == 0.0

    def test_metrics_with_empty_trades(self):
        """Should handle backtest with no executed trades."""
        result = make_backtest_result(
            starting_cash=10000.0,
            final_equity=10000.0,
            trades=[],
        )

        metrics = compute_metrics(result)

        assert metrics["total_trades"] == 0
        assert metrics["win_rate"] == 0.0
        assert metrics["sharpe_ratio"] == 0.0
        assert metrics["sortino_ratio"] == 0.0
        assert metrics["max_drawdown"] == 0.0
        assert metrics["volatility"] == 0.0

    def test_metrics_with_multiple_trades(self):
        """Should calculate metrics with multiple trades covering edge cases."""
        trades = [
            ExecutedTrade(
                timestamp=datetime(2024, 1, i + 1, 12, 0, 0, tzinfo=timezone.utc),
                market_id="0x123",
                side="buy" if i % 2 == 0 else "sell",
                price=0.50 + (i * 0.01),
                size=100.0,
                shares=200.0,
                slippage_bps=10.0,
                fee=5.0,
            )
            for i in range(5)
        ]

        result = make_backtest_result(
            starting_cash=10000.0,
            final_equity=10250.0,
            trades=trades,
            commission_rate=0.01,
        )

        metrics = compute_metrics(result)

        assert metrics["total_trades"] == 5
        assert metrics["total_fees"] == 25.0  # 5 trades * $5 fee
        assert isinstance(metrics["sharpe_ratio"], float)
        assert isinstance(metrics["sortino_ratio"], float)
        assert 0 <= metrics["max_drawdown"] <= 1

    def test_win_rate_calculation(self):
        """Should calculate win rate correctly."""
        # Create 3 winning and 2 losing trades
        trades = []
        for i in range(5):
            trade = ExecutedTrade(
                timestamp=datetime(2024, 1, i + 1, 12, 0, 0, tzinfo=timezone.utc),
                market_id="0x123",
                side="sell" if i < 3 else "buy",  # First 3 are sells (winners)
                price=0.50,
                size=100.0 if i < 3 else 90.0,  # Losers have smaller size (loss)
                shares=200.0,
                slippage_bps=10.0,
                fee=0.0,
            )
            trades.append(trade)

        result = make_backtest_result(
            starting_cash=10000.0,
            final_equity=10200.0,
            trades=trades,
        )

        metrics = compute_metrics(result)

        # Should calculate win rate based on profitable trades
        assert 0 <= metrics["win_rate"] <= 1
        assert metrics["winning_trades"] + metrics["losing_trades"] == 5

    def test_skip_rate_with_skipped_trades(self):
        """Should calculate skip rate when trades are skipped."""
        trades = [
            ExecutedTrade(
                timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                market_id="0x123",
                side="buy",
                price=0.50,
                size=100.0,
                shares=200.0,
                slippage_bps=10.0,
                fee=0.0,
            )
        ]

        # Create 3 skipped trades with all required fields
        skipped = [
            Trade(
                transaction_hash=f"0xtx{i}",
                timestamp=datetime(2024, 1, i + 2, 12, 0, 0, tzinfo=timezone.utc),
                maker="0xmaker",
                market_id=f"0x{i}",
                side="buy",
                price=0.50,
                size=100.0,
                outcome="yes",
                match_hash=f"0xmatch{i}",
            )
            for i in range(3)
        ]

        result = make_backtest_result(
            starting_cash=10000.0,
            final_equity=10000.0,
            trades=trades,
            skipped=skipped,
        )

        metrics = compute_metrics(result)

        # 1 executed, 3 skipped = 25% execution, 75% skip rate
        assert metrics["total_trades"] == 1
        assert metrics["skipped_trades"] == 3
        assert metrics["skip_rate"] == 0.75

    def test_equity_curve_generation(self):
        """Should generate equity curve from trades."""
        trades = [
            ExecutedTrade(
                timestamp=datetime(2024, 1, i + 1, 12, 0, 0, tzinfo=timezone.utc),
                market_id="0x123",
                side="buy",
                price=0.50,
                size=100.0,
                shares=200.0,
                slippage_bps=10.0,
                fee=0.0,
            )
            for i in range(3)
        ]

        result = make_backtest_result(
            starting_cash=10000.0,
            final_equity=10000.0,
            trades=trades,
        )

        metrics = compute_metrics(result)

        # Should have equity curve with multiple points
        assert "equity_curve" in metrics
        assert len(metrics["equity_curve"]) >= 1
        assert metrics["peak_equity"] >= 10000.0

    def test_exposure_metrics(self):
        """Should calculate exposure metrics."""
        trades = [
            ExecutedTrade(
                timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                market_id="0x123",
                side="buy",
                price=0.50,
                size=500.0,
                shares=1000.0,
                slippage_bps=10.0,
                fee=0.0,
            )
        ]

        result = make_backtest_result(
            starting_cash=10000.0,
            final_equity=10000.0,
            trades=trades,
        )

        metrics = compute_metrics(result)

        assert metrics["max_exposure"] >= 0
        assert metrics["avg_exposure"] >= 0

    def test_absolute_profit_calculation(self):
        """Should calculate absolute profit correctly."""
        trades = [
            ExecutedTrade(
                timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                market_id="0x123",
                side="buy",
                price=0.50,
                size=100.0,
                shares=200.0,
                slippage_bps=10.0,
                fee=0.0,
            )
        ]

        result = make_backtest_result(
            starting_cash=10000.0,
            final_equity=10500.0,  # $500 profit
            trades=trades,
        )

        metrics = compute_metrics(result)

        assert metrics["absolute_profit"] == 500.0
        assert metrics["total_return"] == 0.05

    def test_division_by_zero_protection(self):
        """Should handle division by zero when no trades exist."""
        result = make_backtest_result(
            starting_cash=10000.0,
            final_equity=10000.0,
            trades=[],
        )

        metrics = compute_metrics(result)

        # These should not raise division by zero errors
        assert metrics["win_rate"] == 0.0
        assert metrics["skip_rate"] == 0.0
        assert metrics["avg_trade_return"] == 0.0
        assert metrics["median_trade_return"] == 0.0
        assert metrics["std_trade_return"] == 0.0


class TestFormatMetrics:
    """Tests for format_metrics function."""

    def test_format_metrics_output(self):
        """Should format metrics dict as readable string."""
        metrics = {
            "total_return": 0.12,
            "total_return_pct": 12.0,
            "final_equity": 11200.0,
            "absolute_profit": 1200.0,
            "sharpe_ratio": 1.5,
            "sortino_ratio": 2.0,
            "max_drawdown": 0.05,
            "max_drawdown_pct": 5.0,
            "volatility": 0.1,
            "volatility_pct": 10.0,
            "total_trades": 10,
            "win_rate": 0.6,
            "win_rate_pct": 60.0,
            "avg_trade_return": 0.01,
            "skipped_trades": 2,
            "skip_rate": 0.17,
            "skip_rate_pct": 17.0,
            "max_exposure": 5000.0,
            "avg_exposure": 2000.0,
            "total_fees": 25.0,
        }

        formatted = format_metrics(metrics)

        assert "Backtest Performance" in formatted
        assert "12.00%" in formatted
        assert "$1200.00" in formatted or "1200" in formatted
        assert "Sharpe" in formatted
        assert "10" in formatted  # total trades

    def test_format_metrics_with_zero_values(self):
        """Should handle zero values gracefully."""
        metrics = {
            "total_return": 0.0,
            "total_return_pct": 0.0,
            "final_equity": 10000.0,
            "absolute_profit": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "max_drawdown": 0.0,
            "max_drawdown_pct": 0.0,
            "volatility": 0.0,
            "volatility_pct": 0.0,
            "total_trades": 0,
            "win_rate": 0.0,
            "win_rate_pct": 0.0,
            "avg_trade_return": 0.0,
            "skipped_trades": 0,
            "skip_rate": 0.0,
            "skip_rate_pct": 0.0,
            "max_exposure": 0.0,
            "avg_exposure": 0.0,
            "total_fees": 0.0,
        }

        formatted = format_metrics(metrics)

        assert "0.00%" in formatted
        assert "$10000" in formatted or "10000" in formatted

    def test_format_metrics_includes_all_sections(self):
        """Should include all metric sections."""
        metrics = {
            "total_return": 0.05,
            "total_return_pct": 5.0,
            "final_equity": 10500.0,
            "absolute_profit": 500.0,
            "sharpe_ratio": 0.8,
            "sortino_ratio": 1.2,
            "max_drawdown": 0.03,
            "max_drawdown_pct": 3.0,
            "volatility": 0.08,
            "volatility_pct": 8.0,
            "total_trades": 5,
            "win_rate": 0.6,
            "win_rate_pct": 60.0,
            "avg_trade_return": 0.01,
            "median_trade_return": 0.008,
            "std_trade_return": 0.02,
            "skipped_trades": 1,
            "skip_rate": 0.17,
            "skip_rate_pct": 17.0,
            "max_exposure": 5000.0,
            "avg_exposure": 2000.0,
            "total_fees": 25.0,
        }

        formatted = format_metrics(metrics)

        # Check for key sections
        assert "Returns" in formatted or "Return" in formatted
        assert "Risk-Adjusted" in formatted
        assert "Trading" in formatted
        assert "Capital" in formatted or "Costs" in formatted
