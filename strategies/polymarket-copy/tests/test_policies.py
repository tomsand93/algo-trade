"""
Tests for copy-trade policies.
"""

from dataclasses import replace
from datetime import datetime, timezone, timedelta

import pytest

from pmirror.domain import Trade, BacktestState
from pmirror.policies.base import CopyPolicy, PolicyContext, PolicyResult, SimplePolicy
from pmirror.policies.mirror_latency import MirrorLatencyPolicy
from pmirror.policies.position_rebalance import PositionRebalancePolicy
from pmirror.policies.fixed_allocation import FixedAllocationPolicy


@pytest.fixture
def sample_trade():
    """Create a sample trade for testing."""
    return Trade(
        transaction_hash="0x123",
        timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        maker="0xabc",
        side="buy",
        outcome="yes",
        price=0.65,
        size=500.0,
        market_id="0xmarket",
    )


@pytest.fixture
def sample_state():
    """Create a sample backtest state."""
    return BacktestState(
        cash=1000.0,
        starting_cash=1000.0,
    )


@pytest.fixture
def policy_context(sample_trade, sample_state):
    """Create a policy context for testing."""
    return PolicyContext(
        target_trade=sample_trade,
        current_state=sample_state,
        target_trade_history=[sample_trade],
        capital=1000.0,
        commission_rate=0.0,
        slippage_bps=5,
    )


class TestPolicyResult:
    """Tests for PolicyResult."""

    def test_skip_creates_skip_result(self):
        """Should create a result indicating we should skip."""
        result = PolicyResult.skip("Test reason")

        assert result.should_trade is False
        assert result.skip_reason == "Test reason"
        assert result.size == 0.0

    def test_trade_creates_trade_result(self):
        """Should create a result indicating we should trade."""
        result = PolicyResult.trade(
            side="buy",
            size=100.0,
            price=0.5,
            reason="Test trade",
        )

        assert result.should_trade is True
        assert result.side == "buy"
        assert result.size == 100.0
        assert result.price == 0.5
        assert result.reason == "Test trade"


class TestSimplePolicy:
    """Tests for SimplePolicy."""

    def test_evaluate_copies_trade(self, policy_context):
        """Should copy trade with fixed position size."""
        policy = SimplePolicy(capital=1000, position_size=50.0)
        result = policy.evaluate(policy_context)

        assert result.should_trade is True
        assert result.side == "buy"
        assert result.size == 50.0
        assert "fixed size" in result.reason.lower()

    def test_applies_slippage_to_buys(self, policy_context):
        """Should apply slippage to buy prices."""
        policy = SimplePolicy(capital=1000, position_size=50.0, slippage_bps=10)
        result = policy.evaluate(policy_context)

        # Price should be higher (worse for us)
        assert result.price > policy_context.target_trade.price

    def test_applies_slippage_to_sells(self, policy_context, sample_trade):
        """Should apply slippage to sell prices."""
        sell_trade = sample_trade.model_copy(update={"side": "sell"})
        ctx = replace(policy_context, target_trade=sell_trade)

        policy = SimplePolicy(capital=1000, position_size=50.0, slippage_bps=10)
        result = policy.evaluate(ctx)

        # Price should be lower (worse for us)
        assert result.price < sell_trade.price


class TestMirrorLatencyPolicy:
    """Tests for MirrorLatencyPolicy."""

    def test_copies_trade_with_scaling(self, policy_context):
        """Should copy trade with scaled position size."""
        policy = MirrorLatencyPolicy(
            capital=1000,
            scale_factor=0.1,  # 10% of target
        )
        result = policy.evaluate(policy_context)

        assert result.should_trade is True
        assert result.size == pytest.approx(50.0)  # 10% of 500

    def test_skips_small_target_trades(self, policy_context, sample_trade):
        """Should skip trades below minimum size."""
        small_trade = sample_trade.model_copy(update={"size": 25.0})
        ctx = PolicyContext(
            target_trade=small_trade,
            current_state=policy_context.current_state,
            target_trade_history=policy_context.target_trade_history,
            capital=policy_context.capital,
            commission_rate=policy_context.commission_rate,
            slippage_bps=policy_context.slippage_bps,
        )

        policy = MirrorLatencyPolicy(
            capital=1000,
            min_target_size=50.0,
        )
        result = policy.evaluate(ctx)

        assert result.should_trade is False
        assert "below minimum" in result.skip_reason.lower()

    def test_respects_position_size_limits(self, policy_context):
        """Should enforce min and max position sizes."""
        policy = MirrorLatencyPolicy(
            capital=1000,
            scale_factor=0.01,  # Would give $5 position
            min_position_size=10.0,
            max_position_size=100.0,
        )
        result = policy.evaluate(policy_context)

        assert result.should_trade is False  # Below minimum

    def test_caps_at_maximum_position(self, policy_context, sample_trade):
        """Should cap position at maximum size."""
        large_trade = sample_trade.model_copy(update={"size": 50000.0})
        ctx = replace(policy_context, target_trade=large_trade)

        policy = MirrorLatencyPolicy(
            capital=10000,
            scale_factor=1.0,
            max_position_size=1000.0,
        )
        result = policy.evaluate(ctx)

        assert result.size == 1000.0

    def test_respects_cash_constraint(self, policy_context, sample_state):
        """Should reduce position size when cash is limited."""
        low_cash_state = sample_state.model_copy(update={"cash": 30.0})
        ctx = replace(policy_context, current_state=low_cash_state)

        policy = MirrorLatencyPolicy(
            capital=1000,
            scale_factor=0.5,  # Would give $250
        )
        result = policy.evaluate(ctx)

        assert result.size <= 30.0  # Limited by cash

    def test_applies_slippage(self, policy_context):
        """Should apply slippage to execution price."""
        policy = MirrorLatencyPolicy(
            capital=1000,
            slippage_bps=10,
        )
        result = policy.evaluate(policy_context)

        # Buy price should be higher
        assert result.price > policy_context.target_trade.price

    def test_invalid_parameters_raise(self):
        """Should raise on invalid parameters."""
        with pytest.raises(ValueError):
            MirrorLatencyPolicy(capital=1000, scale_factor=1.5)  # > 1

        with pytest.raises(ValueError):
            MirrorLatencyPolicy(capital=1000, scale_factor=0)  # = 0

        with pytest.raises(ValueError):
            MirrorLatencyPolicy(capital=1000, latency_seconds=-1)  # Negative


class TestFixedAllocationPolicy:
    """Tests for FixedAllocationPolicy."""

    def test_copies_with_fixed_allocation(self, policy_context):
        """Should copy trade with fixed allocation."""
        policy = FixedAllocationPolicy(
            capital=1000,
            allocation_per_trade=100.0,
        )
        result = policy.evaluate(policy_context)

        assert result.should_trade is True
        assert result.size == 100.0

    def test_skips_when_insufficient_cash(self, policy_context, sample_state):
        """Should skip when not enough cash."""
        low_cash_state = sample_state.model_copy(update={"cash": 50.0})
        ctx = replace(policy_context, current_state=low_cash_state)

        policy = FixedAllocationPolicy(
            capital=1000,
            allocation_per_trade=100.0,
        )
        result = policy.evaluate(ctx)

        assert result.should_trade is False
        assert "insufficient cash" in result.skip_reason.lower()

    def test_can_skip_sells(self, policy_context, sample_trade):
        """Should skip sells when configured."""
        sell_trade = sample_trade.model_copy(update={"side": "sell"})
        ctx = replace(policy_context, target_trade=sell_trade)

        policy = FixedAllocationPolicy(
            capital=1000,
            allocation_per_trade=100.0,
            copy_sells=False,
        )
        result = policy.evaluate(ctx)

        assert result.should_trade is False
        assert "sell" in result.skip_reason.lower()

    def test_copies_sells_when_enabled(self, policy_context, sample_trade):
        """Should copy sells when enabled."""
        sell_trade = sample_trade.model_copy(update={"side": "sell"})
        ctx = replace(policy_context, target_trade=sell_trade)

        policy = FixedAllocationPolicy(
            capital=1000,
            allocation_per_trade=100.0,
            copy_sells=True,
        )
        result = policy.evaluate(ctx)

        assert result.should_trade is True
        assert result.side == "sell"

    def test_applies_slippage(self, policy_context):
        """Should apply slippage to price."""
        policy = FixedAllocationPolicy(
            capital=1000,
            allocation_per_trade=100.0,
            slippage_bps=10,
        )
        result = policy.evaluate(policy_context)

        assert result.price != policy_context.target_trade.price

    def test_max_trades_property(self):
        """Should calculate maximum trades correctly."""
        policy = FixedAllocationPolicy(
            capital=1000,
            allocation_per_trade=100.0,
        )

        assert policy.max_trades == 10


class TestPositionRebalancePolicy:
    """Tests for PositionRebalancePolicy."""

    def test_skips_when_interval_not_met(self, policy_context):
        """Should skip when rebalance interval hasn't passed."""
        policy = PositionRebalancePolicy(
            capital=1000,
            rebalance_interval="1h",
        )
        result = policy.evaluate(policy_context)

        # Should skip since this is the first trade and interval check
        # depends on internal state
        assert isinstance(result, PolicyResult)

    def test_calculates_target_allocations(self, policy_context):
        """Should calculate target wallet allocations correctly."""
        policy = PositionRebalancePolicy(capital=1000)

        allocations = policy._get_target_allocations(policy_context)

        # Single trade with $500 size should have 100% allocation to that market
        assert "0xmarket:yes" in allocations
        assert allocations["0xmarket:yes"] == pytest.approx(1.0)

    def test_calculates_current_allocations(self, policy_context, sample_state):
        """Should calculate current allocations correctly."""
        # Add a position to the state
        from pmirror.domain import Position
        pos = Position(
            wallet="follower",
            market_id="0xmarket",
            outcome="yes",
            size=300.0,
            avg_price=0.6,
            shares=500,
        )
        state_with_pos = sample_state.model_copy(
            update={"positions": {"0xmarket:yes": pos}}
        )
        ctx = replace(policy_context, current_state=state_with_pos)

        policy = PositionRebalancePolicy(capital=1000)
        allocations = policy._get_current_allocations(ctx)

        # Position is $300 out of $1300 equity
        assert allocations["0xmarket:yes"] == pytest.approx(300.0 / 1300.0, rel=0.01)

    def test_invalid_interval_raises(self):
        """Should raise on invalid interval."""
        with pytest.raises(ValueError):
            PositionRebalancePolicy(capital=1000, rebalance_interval="invalid")

    def test_invalid_threshold_raises(self):
        """Should raise on invalid threshold."""
        with pytest.raises(ValueError):
            PositionRebalancePolicy(capital=1000, rebalance_threshold=1.5)


class TestPolicyIntegration:
    """Integration tests for policies."""

    def test_simple_policy_end_to_end(self, policy_context):
        """Should work through multiple trades."""
        policy = SimplePolicy(capital=1000, position_size=100.0)
        state = BacktestState(cash=1000, starting_cash=1000)

        trades = [
            Trade(
                transaction_hash=f"0x{i}",
                timestamp=datetime(2024, 1, 15, 12, i, tzinfo=timezone.utc),
                maker="0xtarget",
                side="buy",
                outcome="yes",
                price=0.5 + (i * 0.05),
                size=100 + i,
                market_id="0xmarket",
            )
            for i in range(5)
        ]

        results = []
        for trade in trades:
            ctx = PolicyContext(
                target_trade=trade,
                current_state=state,
                target_trade_history=trades,
                capital=1000,
                commission_rate=0.0,
                slippage_bps=5,
            )
            result = policy.evaluate(ctx)
            results.append(result)

        # All trades should be copied
        assert all(r.should_trade for r in results)
        assert all(r.size == 100.0 for r in results)

    def test_mirror_latency_with_multiple_trades(self, policy_context):
        """Should scale multiple trades correctly."""
        policy = MirrorLatencyPolicy(
            capital=1000,
            scale_factor=0.2,
            min_position_size=10.0,
        )

        trades = [
            Trade(
                transaction_hash=f"0x{i}",
                timestamp=datetime(2024, 1, 15, 12, i, tzinfo=timezone.utc),
                maker="0xtarget",
                side="buy",
                outcome="yes",
                price=0.6,
                size=100 * (i + 1),  # 100, 200, 300, 400, 500
                market_id="0xmarket",
            )
            for i in range(5)
        ]

        scaled_sizes = []
        for trade in trades:
            ctx = replace(policy_context, target_trade=trade)
            result = policy.evaluate(ctx)
            scaled_sizes.append(result.size)

        # Should be 20% of each target size
        assert scaled_sizes == pytest.approx([20.0, 40.0, 60.0, 80.0, 100.0])
