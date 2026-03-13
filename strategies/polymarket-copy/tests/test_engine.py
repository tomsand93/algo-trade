"""
Tests for the backtest engine.
"""

from datetime import datetime, timezone

import pytest

from pmirror.domain import Trade, Market, BacktestState, Position
from pmirror.domain.engine import BacktestEngine, BacktestResult
from pmirror.policies.base import SimplePolicy, PolicyContext
from pmirror.policies.mirror_latency import MirrorLatencyPolicy


class TestBacktestEngine:
    """Tests for BacktestEngine class."""

    def test_simple_backtest(self):
        """Should execute a simple backtest with one trade."""
        policy = SimplePolicy(position_size=100.0)

        target_trades = [
            Trade(
                transaction_hash="0xabc",
                timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                maker="0xwallet",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.65,
                size=1000.0,
                market_id="0x123",
            )
        ]

        markets = {
            "0x123": Market(
                condition_id="0x123",
                question="Test?",
                outcomes=["yes", "no"],
                end_time=None,
                resolution=None,
            )
        }

        engine = BacktestEngine(initial_cash=10000.0)
        result = engine.run(target_trades, markets, policy)

        assert result.initial_cash == 10000.0
        assert len(result.executed_trades) == 1
        assert result.executed_trades[0].size == 100.0
        assert result.skipped_trades == 0

    def test_multiple_trades(self):
        """Should process multiple trades in order."""
        policy = SimplePolicy(position_size=50.0)

        target_trades = [
            Trade(
                transaction_hash=f"0x{i}",
                timestamp=datetime(2024, 1, i, 12, 0, 0, tzinfo=timezone.utc),
                maker="0xwallet",
                taker=None,
                side="buy" if i % 2 == 1 else "sell",
                outcome="yes",
                price=0.5 + (i * 0.05),
                size=100.0,
                market_id="0x123",
            )
            for i in range(1, 6)
        ]

        markets = {
            "0x123": Market(
                condition_id="0x123",
                question="Test?",
                outcomes=["yes", "no"],
                end_time=None,
                resolution=None,
            )
        }

        engine = BacktestEngine(initial_cash=10000.0)
        result = engine.run(target_trades, markets, policy)

        assert len(result.executed_trades) == 5
        assert result.skipped_trades == 0

    def test_skips_trade_when_policy_returns_skip(self):
        """Should skip trade when policy says no."""
        # Use a policy with position_size larger than cash
        policy = SimplePolicy(position_size=50000.0)  # Can't afford

        target_trades = [
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

        markets = {
            "0x123": Market(
                condition_id="0x123",
                question="Test?",
                outcomes=["yes", "no"],
                end_time=None,
                resolution=None,
            )
        }

        engine = BacktestEngine(initial_cash=1000.0)
        result = engine.run(target_trades, markets, policy)

        assert len(result.executed_trades) == 0
        assert result.skipped_trades == 1

    def test_skips_trade_for_unknown_market(self):
        """Should skip trade when market not found."""
        policy = SimplePolicy(position_size=100.0)

        target_trades = [
            Trade(
                transaction_hash="0xabc",
                timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                maker="0xwallet",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.65,
                size=100.0,
                market_id="0xunknown",  # Not in markets dict
            )
        ]

        markets = {}

        engine = BacktestEngine(initial_cash=10000.0)
        result = engine.run(target_trades, markets, policy)

        assert len(result.executed_trades) == 0
        assert result.skipped_trades == 1

    def test_tracks_cash_position(self):
        """Should correctly track cash and positions."""
        policy = SimplePolicy(position_size=100.0)

        target_trades = [
            Trade(
                transaction_hash="0xabc",
                timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                maker="0xwallet",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.50,
                size=100.0,
                market_id="0x123",
            )
        ]

        markets = {
            "0x123": Market(
                condition_id="0x123",
                question="Test?",
                outcomes=["yes", "no"],
                end_time=None,
                resolution=None,
            )
        }

        engine = BacktestEngine(initial_cash=10000.0)
        result = engine.run(target_trades, markets, policy)

        # Bought $100 at $0.50 = spent $100
        assert result.final_cash < 10000.0
        assert result.final_cash == pytest.approx(9900.0, rel=0.01)

    def test_sell_trade_increases_cash(self):
        """Should increase cash when selling."""
        policy = SimplePolicy(position_size=100.0)

        target_trades = [
            Trade(
                transaction_hash="0xabc",
                timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                maker="0xwallet",
                taker=None,
                side="sell",
                outcome="yes",
                price=0.50,
                size=100.0,
                market_id="0x123",
            )
        ]

        markets = {
            "0x123": Market(
                condition_id="0x123",
                question="Test?",
                outcomes=["yes", "no"],
                end_time=None,
                resolution=None,
            )
        }

        engine = BacktestEngine(initial_cash=10000.0)
        result = engine.run(target_trades, markets, policy)

        # Selling increases cash (short position)
        assert result.final_cash > 10000.0

    def test_applies_slippage(self):
        """Should apply slippage to execution prices."""
        policy = SimplePolicy(position_size=100.0, slippage_bps=10)

        target_trades = [
            Trade(
                transaction_hash="0xabc",
                timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                maker="0xwallet",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.50,
                size=100.0,
                market_id="0x123",
            )
        ]

        markets = {
            "0x123": Market(
                condition_id="0x123",
                question="Test?",
                outcomes=["yes", "no"],
                end_time=None,
                resolution=None,
            )
        }

        engine = BacktestEngine(initial_cash=10000.0)
        result = engine.run(target_trades, markets, policy)

        # Buy with 10bps slippage = worse price
        # Price should be higher than 0.50
        assert result.executed_trades[0].price > 0.50

    def test_calculates_total_return(self):
        """Should calculate total return correctly."""
        policy = SimplePolicy(position_size=0.0)  # No trades

        target_trades = []

        markets = {}

        engine = BacktestEngine(initial_cash=10000.0)
        result = engine.run(target_trades, markets, policy)

        assert result.total_return == 0.0

    def test_executes_trades_in_timestamp_order(self):
        """Should execute trades in timestamp order, not input order."""
        policy = SimplePolicy(position_size=100.0)

        # Create trades out of order
        target_trades = [
            Trade(
                transaction_hash="0x3",
                timestamp=datetime(2024, 1, 3, 12, 0, 0, tzinfo=timezone.utc),
                maker="0xwallet",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.50,
                size=100.0,
                market_id="0x123",
            ),
            Trade(
                transaction_hash="0x1",
                timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                maker="0xwallet",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.50,
                size=100.0,
                market_id="0x123",
            ),
            Trade(
                transaction_hash="0x2",
                timestamp=datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc),
                maker="0xwallet",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.50,
                size=100.0,
                market_id="0x123",
            ),
        ]

        markets = {
            "0x123": Market(
                condition_id="0x123",
                question="Test?",
                outcomes=["yes", "no"],
                end_time=None,
                resolution=None,
            )
        }

        engine = BacktestEngine(initial_cash=10000.0)
        result = engine.run(target_trades, markets, policy)

        # Should execute in order: 0x1, 0x2, 0x3
        assert result.executed_trades[0].target_trade_hash == "0x1"
        assert result.executed_trades[1].target_trade_hash == "0x2"
        assert result.executed_trades[2].target_trade_hash == "0x3"

    def test_commission_reduces_cash(self):
        """Should deduct commission from cash."""
        policy = SimplePolicy(position_size=100.0)

        target_trades = [
            Trade(
                transaction_hash="0xabc",
                timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                maker="0xwallet",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.50,
                size=100.0,
                market_id="0x123",
            )
        ]

        markets = {
            "0x123": Market(
                condition_id="0x123",
                question="Test?",
                outcomes=["yes", "no"],
                end_time=None,
                resolution=None,
            )
        }

        engine = BacktestEngine(initial_cash=10000.0, commission_rate=0.01)  # 1% commission
        result = engine.run(target_trades, markets, policy)

        # Trade: 100 shares * $0.50 = $50 cost
        # Commission: $50 * 1% = $0.50
        # Total: $50.50 spent, final = $9949.50
        assert result.final_cash == pytest.approx(9949.50, rel=0.01)
        assert result.executed_trades[0].fee == 0.50


class TestBacktestResult:
    """Tests for BacktestResult dataclass."""

    def test_backtest_result_attributes(self):
        """Should have all expected attributes."""
        result = BacktestResult(
            initial_cash=10000.0,
            final_cash=10500.0,
            total_return=0.05,
            executed_trades=[],
            skipped_trades=2,
            timestamps=[],
        )

        assert result.initial_cash == 10000.0
        assert result.final_cash == 10500.0
        assert result.total_return == 0.05
        assert result.skipped_trades == 2


class TestBacktestEngineIntegration:
    """Integration tests with actual policies."""

    def test_mirror_latency_policy_integration(self):
        """Should work with MirrorLatencyPolicy."""
        policy = MirrorLatencyPolicy(
            scale_factor=0.1,  # 10% of target trade size
            latency_seconds=0,
        )

        target_trades = [
            Trade(
                transaction_hash="0xabc",
                timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                maker="0xwallet",
                taker=None,
                side="buy",
                outcome="yes",
                price=0.50,
                size=1000.0,  # Target trades $1000
                market_id="0x123",
            )
        ]

        markets = {
            "0x123": Market(
                condition_id="0x123",
                question="Test?",
                outcomes=["yes", "no"],
                end_time=None,
                resolution=None,
            )
        }

        engine = BacktestEngine(initial_cash=10000.0)
        result = engine.run(target_trades, markets, policy)

        # Should trade 10% of $1000 = $100
        assert result.executed_trades[0].size == 100.0
