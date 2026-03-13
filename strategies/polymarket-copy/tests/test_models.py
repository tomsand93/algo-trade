"""
Tests for core domain models.
"""

from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from pmirror.domain import (
    BacktestMetrics,
    BacktestState,
    ExecutedTrade,
    Market,
    Position,
    Trade,
)


class TestMarket:
    """Tests for Market model."""

    def test_create_minimal_market(self):
        """Should create market with required fields."""
        market = Market(
            condition_id="0x123",
            question="Will it rain tomorrow?",
        )
        assert market.condition_id == "0x123"
        assert market.question == "Will it rain tomorrow?"
        assert market.outcomes == ["yes", "no"]  # Default
        assert market.resolution is None

    def test_create_full_market(self):
        """Should create market with all fields."""
        end_time = datetime(2024, 12, 31, 23, 59, 59)
        market = Market(
            condition_id="0x123",
            question="Test question",
            outcomes=["yes", "no", "void"],
            end_time=end_time,
            resolution="yes",
            description="Test description",
            volume=1000000.0,
            liquidity=50000.0,
            created_time=datetime(2024, 1, 1),
        )
        assert market.outcomes == ["yes", "no", "void"]
        assert market.resolution == "yes"
        assert market.volume == 1000000.0

    def test_is_binary_property(self):
        """Should correctly identify binary markets."""
        binary_market = Market(condition_id="0x1", question="Test", outcomes=["yes", "no"])
        assert binary_market.is_binary is True

        multi_market = Market(
            condition_id="0x2", question="Test", outcomes=["a", "b", "c"]
        )
        assert multi_market.is_binary is False

    def test_is_resolved_property(self):
        """Should check if market is resolved."""
        resolved = Market(condition_id="0x1", question="Test", resolution="yes")
        assert resolved.is_resolved is True

        unresolved = Market(condition_id="0x2", question="Test")
        assert unresolved.is_resolved is False

    def test_is_closed_property(self):
        """Should check if market is closed for trading."""
        closed_market = Market(
            condition_id="0x1",
            question="Test",
            end_time=datetime(2020, 1, 1),  # In the past
        )
        assert closed_market.is_closed is True

        open_market = Market(
            condition_id="0x2",
            question="Test",
            end_time=datetime(2030, 1, 1),  # In the future
        )
        assert open_market.is_closed is False

        no_end_time = Market(condition_id="0x3", question="Test")
        assert no_end_time.is_closed is False

    def test_volume_must_be_positive(self):
        """Volume must be non-negative."""
        with pytest.raises(ValidationError):
            Market(condition_id="0x1", question="Test", volume=-100)

    def test_liquidity_must_be_positive(self):
        """Liquidity must be non-negative."""
        with pytest.raises(ValidationError):
            Market(condition_id="0x1", question="Test", liquidity=-50)


class TestTrade:
    """Tests for Trade model."""

    def test_create_trade(self):
        """Should create trade with all fields."""
        timestamp = datetime(2024, 1, 15, 12, 30, 0)
        trade = Trade(
            transaction_hash="0xabcd",
            timestamp=timestamp,
            maker="0xABC123",
            taker="0xDEF456",
            side="buy",
            outcome="yes",
            price=0.65,
            size=100.0,
            market_id="0xmarket",
        )
        assert trade.transaction_hash == "0xabcd"
        assert trade.maker == "0xabc123"  # Lowercased
        assert trade.taker == "0xdef456"  # Lowercased
        assert trade.shares == pytest.approx(100.0 / 0.65)  # Computed

    def test_side_must_be_valid(self):
        """Side must be 'buy' or 'sell'."""
        with pytest.raises(ValidationError):
            Trade(
                transaction_hash="0x1",
                timestamp=datetime.now(),
                maker="0xabc",
                side="invalid",  # Not buy/sell
                outcome="yes",
                price=0.5,
                size=100,
                market_id="0xm",
            )

    def test_price_must_be_between_0_and_1(self):
        """Price represents probability, must be 0-1."""
        with pytest.raises(ValidationError):
            Trade(
                transaction_hash="0x1",
                timestamp=datetime.now(),
                maker="0xabc",
                side="buy",
                outcome="yes",
                price=1.5,  # Too high
                size=100,
                market_id="0xm",
            )

        with pytest.raises(ValidationError):
            Trade(
                transaction_hash="0x1",
                timestamp=datetime.now(),
                maker="0xabc",
                side="buy",
                outcome="yes",
                price=-0.1,  # Negative
                size=100,
                market_id="0xm",
            )

    def test_size_must_be_positive(self):
        """Trade size must be positive."""
        with pytest.raises(ValidationError):
            Trade(
                transaction_hash="0x1",
                timestamp=datetime.now(),
                maker="0xabc",
                side="buy",
                outcome="yes",
                price=0.5,
                size=0,  # Must be > 0
                market_id="0xm",
            )

    def test_addresses_normalized_to_lowercase(self):
        """Ethereum addresses should be lowercased."""
        trade = Trade(
            transaction_hash="0x1",
            timestamp=datetime.now(),
            maker="0xABCDEF123456",
            taker="0xFEDCBA654321",
            side="buy",
            outcome="yes",
            price=0.5,
            size=100,
            market_id="0xm",
        )
        assert trade.maker == "0xabcdef123456"
        assert trade.taker == "0xfedcba654321"

    def test_shares_computed_when_provided(self):
        """Shares can be provided explicitly."""
        trade = Trade(
            transaction_hash="0x1",
            timestamp=datetime.now(),
            maker="0xabc",
            side="buy",
            outcome="yes",
            price=0.5,
            size=100,
            shares=200.0,  # Explicit
            market_id="0xm",
        )
        assert trade.shares == 200.0


class TestPosition:
    """Tests for Position model."""

    def test_create_position(self):
        """Should create position with all fields."""
        position = Position(
            wallet="0xABC123",
            market_id="0xmarket",
            outcome="yes",
            size=500.0,
            avg_price=0.60,
            shares=833.33,
        )
        assert position.wallet == "0xabc123"  # Lowercased
        assert position.size == 500.0
        assert position.unrealized_pnl == 0.0  # Default

    def test_long_position(self):
        """Long position has positive size."""
        position = Position(
            wallet="0xabc",
            market_id="0xm",
            outcome="yes",
            size=1000.0,  # Positive = long
            avg_price=0.50,
            shares=2000.0,
        )
        assert position.size > 0

    def test_short_position(self):
        """Short position has negative size."""
        position = Position(
            wallet="0xabc",
            market_id="0xm",
            outcome="yes",
            size=-500.0,  # Negative = short
            avg_price=0.50,
            shares=-1000.0,
        )
        assert position.size < 0

    def test_address_normalized(self):
        """Wallet address should be lowercased."""
        position = Position(
            wallet="0xABCDEF",
            market_id="0xm",
            outcome="yes",
            size=100,
            avg_price=0.5,
            shares=200,
        )
        assert position.wallet == "0xabcdef"


class TestExecutedTrade:
    """Tests for ExecutedTrade model."""

    def test_create_executed_trade(self):
        """Should create executed trade with all fields."""
        timestamp = datetime(2024, 1, 15, 12, 30, 0)
        trade = ExecutedTrade(
            timestamp=timestamp,
            market_id="0xmarket",
            side="buy",
            price=0.65,
            size=100.0,
            shares=153.85,
            slippage_bps=5.0,
            fee=0.50,
            target_trade_hash="0xtarget",
            reason="mirror_latency",
        )
        assert trade.market_id == "0xmarket"
        assert trade.slippage_bps == 5.0
        assert trade.reason == "mirror_latency"

    def test_default_values(self):
        """Should have sensible defaults."""
        trade = ExecutedTrade(
            timestamp=datetime.now(),
            market_id="0xm",
            side="sell",
            price=0.5,
            size=100,
            shares=200,
        )
        assert trade.slippage_bps == 0.0
        assert trade.fee == 0.0
        assert trade.target_trade_hash is None
        assert trade.reason == ""

    def test_slippage_and_fee_must_be_non_negative(self):
        """Slippage and fee cannot be negative."""
        with pytest.raises(ValidationError):
            ExecutedTrade(
                timestamp=datetime.now(),
                market_id="0xm",
                side="buy",
                price=0.5,
                size=100,
                shares=200,
                slippage_bps=-5.0,  # Invalid
            )

        with pytest.raises(ValidationError):
            ExecutedTrade(
                timestamp=datetime.now(),
                market_id="0xm",
                side="buy",
                price=0.5,
                size=100,
                shares=200,
                fee=-1.0,  # Invalid
            )


class TestBacktestState:
    """Tests for BacktestState model."""

    def test_create_state(self):
        """Should create backtest state."""
        state = BacktestState(
            cash=1000.0,
            starting_cash=1000.0,
        )
        assert state.cash == 1000.0
        assert state.positions == {}
        assert state.trade_log == []
        assert state.timestamps == []

    def test_equity_property(self):
        """Equity should be cash + position values."""
        state = BacktestState(
            cash=500.0,
            starting_cash=1000.0,
            positions={
                "0xm1:yes": Position(
                    wallet="follower", market_id="0xm1", outcome="yes", size=300.0, avg_price=0.6, shares=500
                ),
                "0xm2:no": Position(
                    wallet="follower", market_id="0xm2", outcome="no", size=200.0, avg_price=0.4, shares=500
                ),
            },
        )
        assert state.equity == 1000.0  # 500 cash + 300 + 200 positions

    def test_total_return_property(self):
        """Should calculate return relative to starting capital."""
        state = BacktestState(
            cash=1500.0,
            starting_cash=1000.0,
        )
        assert state.total_return == 0.5  # 50% return

    def test_exposure_property(self):
        """Exposure should sum absolute position sizes."""
        state = BacktestState(
            cash=500.0,
            starting_cash=1000.0,
            positions={
                "0xm1:yes": Position(
                    wallet="follower", market_id="0xm1", outcome="yes", size=300.0, avg_price=0.6, shares=500
                ),
                "0xm2:no": Position(
                    wallet="follower", market_id="0xm2", outcome="no", size=-200.0, avg_price=0.4, shares=-500
                ),
            },
        )
        assert state.exposure == 500.0  # |300| + |-200|

    def test_get_position(self):
        """Should retrieve position by market and outcome."""
        pos = Position(wallet="w", market_id="0xm", outcome="yes", size=100, avg_price=0.5, shares=200)
        state = BacktestState(cash=1000, starting_cash=1000, positions={"0xm:yes": pos})

        assert state.get_position("0xm", "yes") is pos
        assert state.get_position("0xm", "no") is None

    def test_update_position_new(self):
        """Should create new position."""
        state = BacktestState(cash=1000, starting_cash=1000)
        state.update_position(market_id="0xm", outcome="yes", size_delta=100, price=0.5)

        assert "0xm:yes" in state.positions
        pos = state.positions["0xm:yes"]
        assert pos.size == 100
        assert pos.avg_price == 0.5

    def test_update_position_increase(self):
        """Should increase existing position."""
        pos = Position(wallet="w", market_id="0xm", outcome="yes", size=100, avg_price=0.5, shares=200)
        state = BacktestState(cash=1000, starting_cash=1000, positions={"0xm:yes": pos})
        state.update_position(market_id="0xm", outcome="yes", size_delta=50, price=0.6)

        updated = state.positions["0xm:yes"]
        assert updated.size == 150  # 100 + 50

    def test_update_position_close(self):
        """Should close position when size near zero."""
        pos = Position(wallet="w", market_id="0xm", outcome="yes", size=100, avg_price=0.5, shares=200)
        state = BacktestState(cash=1000, starting_cash=1000, positions={"0xm:yes": pos})
        state.update_position(market_id="0xm", outcome="yes", size_delta=-100, price=0.6)

        assert "0xm:yes" not in state.positions  # Position closed

    def test_update_position_small_delta_ignored(self):
        """Very small deltas should not create positions."""
        state = BacktestState(cash=1000, starting_cash=1000)
        state.update_position(market_id="0xm", outcome="yes", size_delta=0.005, price=0.5)

        assert "0xm:yes" not in state.positions  # Too small


class TestBacktestMetrics:
    """Tests for BacktestMetrics model."""

    def test_create_metrics(self):
        """Should create metrics with all fields."""
        metrics = BacktestMetrics(
            total_return=0.15,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown=0.10,
            max_drawdown_duration=timedelta(days=30),
            total_trades=100,
            win_rate=0.55,
            avg_trade_return=0.01,
            skipped_trades=20,
            skipped_rate=0.20,
            max_exposure=800.0,
            avg_exposure=500.0,
            target_return=0.25,
            final_equity=1150.0,
            peak_equity=1200.0,
        )
        assert metrics.total_return == 0.15
        assert metrics.total_trades == 100

    def test_return_percentage_formatter(self):
        """Should format return as percentage string."""
        metrics = BacktestMetrics(
            total_return=0.1523,
            sharpe_ratio=1.0,
            sortino_ratio=1.0,
            max_drawdown=0.10,
            max_drawdown_duration=timedelta(days=1),
            total_trades=10,
            win_rate=0.5,
            avg_trade_return=0.01,
            skipped_trades=0,
            skipped_rate=0.0,
            max_exposure=100,
            avg_exposure=100,
            target_return=0.1,
            final_equity=100,
            peak_equity=100,
        )
        assert metrics.total_return_pct == "15.23%"

    def test_win_rate_percentage_formatter(self):
        """Should format win rate as percentage string."""
        metrics = BacktestMetrics(
            total_return=0.1,
            sharpe_ratio=1.0,
            sortino_ratio=1.0,
            max_drawdown=0.10,
            max_drawdown_duration=timedelta(days=1),
            total_trades=10,
            win_rate=0.625,
            avg_trade_return=0.01,
            skipped_trades=0,
            skipped_rate=0.0,
            max_exposure=100,
            avg_exposure=100,
            target_return=0.1,
            final_equity=100,
            peak_equity=100,
        )
        assert metrics.win_rate_pct == "62.5%"

    def test_validation_constraints(self):
        """Should validate field constraints."""
        # max_drawdown must be 0-1
        with pytest.raises(ValidationError):
            BacktestMetrics(
                total_return=0.1,
                sharpe_ratio=1.0,
                sortino_ratio=1.0,
                max_drawdown=1.5,  # Invalid > 1
                max_drawdown_duration=timedelta(days=1),
                total_trades=10,
                win_rate=0.5,
                avg_trade_return=0.01,
                skipped_trades=0,
                skipped_rate=0.0,
                max_exposure=100,
                avg_exposure=100,
                target_return=0.1,
                final_equity=100,
                peak_equity=100,
            )

        # win_rate must be 0-1
        with pytest.raises(ValidationError):
            BacktestMetrics(
                total_return=0.1,
                sharpe_ratio=1.0,
                sortino_ratio=1.0,
                max_drawdown=0.1,
                max_drawdown_duration=timedelta(days=1),
                total_trades=10,
                win_rate=1.5,  # Invalid > 1
                avg_trade_return=0.01,
                skipped_trades=0,
                skipped_rate=0.0,
                max_exposure=100,
                avg_exposure=100,
                target_return=0.1,
                final_equity=100,
                peak_equity=100,
            )

    def test_exposure_by_market_default(self):
        """Exposure by market should default to empty dict."""
        metrics = BacktestMetrics(
            total_return=0.1,
            sharpe_ratio=1.0,
            sortino_ratio=1.0,
            max_drawdown=0.1,
            max_drawdown_duration=timedelta(days=1),
            total_trades=10,
            win_rate=0.5,
            avg_trade_return=0.01,
            skipped_trades=0,
            skipped_rate=0.0,
            max_exposure=100,
            avg_exposure=100,
            target_return=0.1,
            final_equity=100,
            peak_equity=100,
        )
        assert metrics.exposure_by_market == {}
        assert metrics.total_fees == 0.0

    def test_correlation_can_be_none(self):
        """Correlation is optional."""
        metrics = BacktestMetrics(
            total_return=0.1,
            sharpe_ratio=1.0,
            sortino_ratio=1.0,
            max_drawdown=0.1,
            max_drawdown_duration=timedelta(days=1),
            total_trades=10,
            win_rate=0.5,
            avg_trade_return=0.01,
            skipped_trades=0,
            skipped_rate=0.0,
            max_exposure=100,
            avg_exposure=100,
            target_return=0.1,
            correlation=None,
            final_equity=100,
            peak_equity=100,
        )
        assert metrics.correlation is None
