"""
Tests for the backtest engine.
"""

from datetime import datetime, timezone, timedelta

import pytest

from pmirror.domain import Trade, BacktestState
from pmirror.backtest.engine import (
    BacktestEngine,
    BacktestConfig,
    BacktestResult,
    run_simple_backtest,
)
from pmirror.backtest.runner import BacktestRunner, run_backtest
from pmirror.policies.mirror_latency import MirrorLatencyPolicy
from pmirror.policies.fixed_allocation import FixedAllocationPolicy


@pytest.fixture
def sample_trades():
    """Create sample target wallet trades."""
    return [
        Trade(
            transaction_hash=f"0x{i}",
            timestamp=datetime(2024, 1, 15, 12, i, tzinfo=timezone.utc),
            maker="0xtarget",
            side="buy",
            outcome="yes",
            price=0.5 + (i * 0.05),
            size=100 + (i * 10),
            market_id="0xmarket",
        )
        for i in range(5)
    ]


@pytest.fixture
def sample_config():
    """Create a sample backtest config."""
    return BacktestConfig(
        target_wallet="0xtarget",
        capital=1000.0,
        scale_factor=0.1,
        commission_rate=0.0,
        slippage_bps=5,
    )


class TestBacktestConfig:
    """Tests for BacktestConfig."""

    def test_creates_default_policy(self):
        """Should create MirrorLatencyPolicy if none provided."""
        config = BacktestConfig(
            target_wallet="0xtest",
            capital=1000,
            scale_factor=0.2,
        )

        assert isinstance(config.policy, MirrorLatencyPolicy)
        assert config.policy.scale_factor == 0.2

    def test_uses_provided_policy(self):
        """Should use provided policy."""
        policy = FixedAllocationPolicy(capital=1000, allocation_per_trade=50)
        config = BacktestConfig(
            target_wallet="0xtest",
            capital=1000,
            policy=policy,
        )

        assert config.policy is policy


class TestBacktestEngine:
    """Tests for BacktestEngine."""

    def test_initialization(self, sample_config):
        """Should initialize with config and empty state."""
        engine = BacktestEngine(sample_config)

        assert engine.config is sample_config
        assert engine.state.cash == 1000.0
        assert engine.state.starting_cash == 1000.0
        assert len(engine.executed_trades) == 0
        assert len(engine.skipped_trades) == 0

    def test_run_processes_trades(self, sample_config, sample_trades):
        """Should process all trades and return result."""
        engine = BacktestEngine(sample_config)
        result = engine.run(sample_trades)

        assert isinstance(result, BacktestResult)
        assert len(result.executed_trades) > 0

    def test_run_updates_cash(self, sample_config, sample_trades):
        """Should decrease cash when buying."""
        engine = BacktestEngine(sample_config)
        initial_cash = engine.state.cash
        result = engine.run(sample_trades)

        # Cash should have decreased (we bought)
        assert result.final_state.cash < initial_cash

    def test_run_creates_positions(self, sample_config, sample_trades):
        """Should create positions from trades."""
        engine = BacktestEngine(sample_config)
        result = engine.run(sample_trades)

        # Should have at least one position
        assert len(result.final_state.positions) > 0

    def test_filter_by_date_range(self, sample_config, sample_trades):
        """Should filter trades by date range."""
        from dataclasses import replace

        start = datetime(2024, 1, 15, 12, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 15, 12, 3, tzinfo=timezone.utc)

        config = replace(sample_config, start_date=start, end_date=end)
        engine = BacktestEngine(config)
        result = engine.run(sample_trades)

        # Should only process trades 1 and 2 (within range)
        # Trade 0 is at 12:00 (before start)
        # Trade 3 is at 12:03 (at end, exclusive)
        assert len(result.executed_trades) <= 2

    def test_reset_clears_state(self, sample_config, sample_trades):
        """Should reset engine to initial state."""
        engine = BacktestEngine(sample_config)
        engine.run(sample_trades)

        engine.reset()

        assert engine.state.cash == sample_config.capital
        assert len(engine.executed_trades) == 0
        assert len(engine.skipped_trades) == 0

    def test_skips_trades_when_policy_says_skip(self, sample_config, sample_trades):
        """Should skip trades when policy returns skip result."""
        # Use policy that skips sells
        policy = FixedAllocationPolicy(
            capital=1000,
            allocation_per_trade=100,
            copy_sells=False,  # Skip all sells
        )
        # Create sample trades with sells
        sell_trades = [
            Trade(
                transaction_hash=f"0x{i}",
                timestamp=datetime(2024, 1, 15, 12, i, tzinfo=timezone.utc),
                maker="0xtarget",
                side="sell",  # All sells
                outcome="yes",
                price=0.5 + (i * 0.05),
                size=100 + (i * 10),
                market_id="0xmarket",
            )
            for i in range(3)
        ]

        config = BacktestConfig(
            target_wallet="0xtest",
            capital=1000,
            policy=policy,
        )
        engine = BacktestEngine(config)
        result = engine.run(sell_trades)

        # All trades should be skipped
        assert len(result.executed_trades) == 0
        assert len(result.skipped_trades) == len(sell_trades)


class TestBacktestResult:
    """Tests for BacktestResult."""

    def test_total_return_property(self):
        """Should calculate total return correctly."""
        state = BacktestState(cash=1200, starting_cash=1000)
        result = BacktestResult(final_state=state)

        assert result.total_return == 0.2  # 20%

    def test_total_trades_property(self):
        """Should return number of executed trades."""
        from pmirror.domain import ExecutedTrade

        trades = [
            ExecutedTrade(
                timestamp=datetime.now(timezone.utc),
                market_id="0xm",
                side="buy",
                price=0.5,
                size=100,
                shares=200,
            )
        ]
        result = BacktestResult(
            final_state=BacktestState(cash=1000, starting_cash=1000),
            executed_trades=trades,
        )

        assert result.total_trades == 1

    def test_skipped_count_property(self):
        """Should return number of skipped trades."""
        skipped = [
            Trade(
                transaction_hash="0x1",
                timestamp=datetime.now(timezone.utc),
                maker="0xtest",
                side="buy",
                outcome="yes",
                price=0.5,
                size=100,
                market_id="0xm",
            )
        ]
        result = BacktestResult(
            final_state=BacktestState(cash=1000, starting_cash=1000),
            skipped_trades=skipped,
        )

        assert result.skipped_count == 1

    def test_skip_rate_calculation(self):
        """Should calculate skip rate correctly."""
        from pmirror.domain import ExecutedTrade

        executed = [
            ExecutedTrade(
                timestamp=datetime.now(timezone.utc),
                market_id="0xm",
                side="buy",
                price=0.5,
                size=100,
                shares=200,
            )
            for _ in range(3)
        ]
        skipped = [
            Trade(
                transaction_hash=f"0x{i}",
                timestamp=datetime.now(timezone.utc),
                maker="0xtest",
                side="buy",
                outcome="yes",
                price=0.5,
                size=100,
                market_id="0xm",
            )
            for i in range(2)
        ]

        result = BacktestResult(
            final_state=BacktestState(cash=1000, starting_cash=1000),
            executed_trades=executed,
            skipped_trades=skipped,
        )

        # 2 skipped out of 5 total = 40%
        assert result.skip_rate == 0.4


class TestRunSimpleBacktest:
    """Tests for run_simple_backtest function."""

    def test_runs_backtest(self, sample_trades):
        """Should run a complete backtest."""
        result = run_simple_backtest(
            target_wallet="0xtarget",
            trades=sample_trades,
            capital=1000,
            scale_factor=0.1,
        )

        assert isinstance(result, BacktestResult)
        assert len(result.executed_trades) > 0

    def test_uses_custom_parameters(self, sample_trades):
        """Should use custom backtest parameters."""
        result = run_simple_backtest(
            target_wallet="0xtarget",
            trades=sample_trades,
            capital=5000,
            scale_factor=0.2,
            slippage_bps=10,
        )

        # Should have executed trades
        assert len(result.executed_trades) > 0


class TestBacktestRunner:
    """Tests for BacktestRunner."""

    def test_initialization(self):
        """Should initialize with or without storage."""
        runner = BacktestRunner()
        assert runner.storage is not None

    def test_creates_policy_by_name(self):
        """Should create policy from name string."""
        runner = BacktestRunner()

        policy = runner._create_policy(
            "mirror_latency",
            capital=1000,
            params={"scale_factor": 0.2},
            commission_rate=0.0,
            slippage_bps=5,
        )

        assert isinstance(policy, MirrorLatencyPolicy)
        assert policy.scale_factor == 0.2

    def test_raises_on_unknown_policy(self):
        """Should raise ValueError for unknown policy name."""
        runner = BacktestRunner()

        with pytest.raises(ValueError, match="Unknown policy"):
            runner._create_policy(
                "unknown_policy",
                capital=1000,
                params={},
                commission_rate=0.0,
                slippage_bps=5,
            )

    def test_creates_fixed_allocation_policy(self):
        """Should create FixedAllocationPolicy."""
        runner = BacktestRunner()

        policy = runner._create_policy(
            "fixed_allocation",
            capital=1000,
            params={"allocation_per_trade": 50},
            commission_rate=0.0,
            slippage_bps=5,
        )

        assert isinstance(policy, FixedAllocationPolicy)

    def test_creates_position_rebalance_policy(self):
        """Should create PositionRebalancePolicy."""
        from pmirror.policies.position_rebalance import PositionRebalancePolicy

        runner = BacktestRunner()

        policy = runner._create_policy(
            "position_rebalance",
            capital=1000,
            params={},
            commission_rate=0.0,
            slippage_bps=5,
        )

        assert isinstance(policy, PositionRebalancePolicy)


class TestIntegration:
    """Integration tests for backtesting."""

    def test_full_backtest_workflow(self, sample_trades):
        """Should run complete backtest workflow."""
        config = BacktestConfig(
            target_wallet="0xtarget",
            capital=1000,
            scale_factor=0.1,
        )

        engine = BacktestEngine(config)
        result = engine.run(sample_trades)

        # Verify result structure
        assert result.final_state is not None
        assert result.config is config
        assert result.start_time is not None
        assert result.end_time is not None
        assert result.processing_time_ms >= 0

    def test_multiple_runs_with_reset(self, sample_config, sample_trades):
        """Should support multiple runs with reset."""
        engine = BacktestEngine(sample_config)

        # First run
        result1 = engine.run(sample_trades)
        trades1 = len(result1.executed_trades)

        # Reset and run again
        engine.reset()
        result2 = engine.run(sample_trades)
        trades2 = len(result2.executed_trades)

        # Should get same results
        assert trades1 == trades2

    def test_backtest_with_commission(self, sample_trades):
        """Should handle commission correctly."""
        config = BacktestConfig(
            target_wallet="0xtarget",
            capital=1000,
            commission_rate=0.01,  # 1%
            scale_factor=0.1,
        )

        engine = BacktestEngine(config)
        result = engine.run(sample_trades)

        # All trades should have fees
        for trade in result.executed_trades:
            assert trade.fee > 0
