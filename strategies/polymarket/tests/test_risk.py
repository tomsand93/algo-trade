"""Tests for RiskManager — all 5 risk controls (RISK-01 through RISK-05).

Each test creates a fresh RiskManager instance to avoid state bleed.
"""
import pytest
from datetime import datetime, timezone, timedelta
from polymarket_bot.risk import RiskManager
from polymarket_bot.models import MarketState, Signal, SimulatedOrder, OpenPosition


# ─── Helpers ────────────────────────────────────────────────────────────────

def make_rm(**kwargs) -> RiskManager:
    """Create a RiskManager with safe defaults, override with kwargs."""
    defaults = dict(
        initial_capital=100.0,
        max_position_size=10.0,
        daily_loss_limit=50.0,
        stop_loss_pct=0.20,
        cooldown_seconds=300,
    )
    defaults.update(kwargs)
    return RiskManager(**defaults)


def make_market_state(market_id="m1", yes_price=0.50) -> MarketState:
    return MarketState(
        market_id=market_id,
        question="Will X happen?",
        yes_price=yes_price,
        no_price=round(1.0 - yes_price, 4),
        volume_24h=1000.0,
        timestamp=datetime.now(timezone.utc),
    )


def make_signal(market_id="m1", direction="BUY_YES", price=0.50) -> Signal:
    return Signal(
        market_id=market_id,
        direction=direction,
        confidence=0.8,
        price=price,
        reason="test signal",
    )


def make_order(market_id="m1", side="YES", fill_price=0.50, quantity=20.0) -> SimulatedOrder:
    return SimulatedOrder(
        market_id=market_id,
        side=side,
        direction="BUY",
        fill_price=fill_price,
        quantity=quantity,
        timestamp=datetime.now(timezone.utc),
    )


# ─── Initial State ──────────────────────────────────────────────────────────

class TestRiskManagerInit:
    def test_not_halted_on_init(self):
        rm = make_rm()
        assert rm.is_halted is False

    def test_check_allows_fresh_signal(self):
        """Fresh RiskManager with no state allows any valid signal."""
        rm = make_rm()
        assert rm.check(make_signal(), make_market_state()) is True


# ─── RISK-01: Max Position Size ─────────────────────────────────────────────

class TestRiskManagerRisk01:
    def test_check_blocks_if_position_already_open(self):
        """RISK-01: Cannot open a second position in the same market."""
        rm = make_rm()
        order = make_order()
        stop_price = 0.40
        rm.record_fill(order, stop_price)
        # Now try to enter the same market again
        assert rm.check(make_signal(), make_market_state()) is False

    def test_check_allows_different_market(self):
        """RISK-01: Separate markets are independent — one open does not block another."""
        rm = make_rm()
        rm.record_fill(make_order(market_id="m1"), 0.40)
        # m2 has no position — should be allowed
        assert rm.check(make_signal(market_id="m2"), make_market_state(market_id="m2")) is True


# ─── RISK-02: Daily Loss Limit ───────────────────────────────────────────────

class TestRiskManagerRisk02:
    def test_check_halts_after_daily_loss_limit(self):
        """RISK-02: After recording a loss equal to daily_loss_limit, check() returns False."""
        rm = make_rm(daily_loss_limit=50.0, initial_capital=100.0)
        # Record a fill then close with a $50 loss
        rm.record_fill(make_order(market_id="m1", fill_price=0.50, quantity=100.0), 0.10)
        rm.record_close("m1", exit_price=0.00)  # loss = (0.00 - 0.50) * 100 = -50.0
        assert rm.is_halted is True
        assert rm.check(make_signal(market_id="m2"), make_market_state(market_id="m2")) is False

    def test_check_blocks_when_pnl_already_at_limit(self):
        """RISK-02: If daily_pnl < -daily_loss_limit before check(), block immediately."""
        rm = make_rm(daily_loss_limit=50.0, initial_capital=100.0)
        rm._daily_pnl = -50.0  # inject state directly for test isolation
        assert rm.check(make_signal(), make_market_state()) is False

    def test_reset_daily_clears_daily_pnl(self):
        """reset_daily() resets daily_pnl to 0 but does not unhalted the manager."""
        rm = make_rm()
        rm._daily_pnl = -30.0
        rm.reset_daily()
        assert rm._daily_pnl == 0.0

    def test_reset_daily_does_not_reset_peak(self):
        """Peak value must NOT reset on daily reset — circuit breakers track all-time drawdown."""
        rm = make_rm(initial_capital=100.0)
        rm._peak_value = 120.0
        rm._portfolio_value = 110.0
        rm.reset_daily()
        assert rm._peak_value == 120.0


# ─── RISK-03: Stop-Loss ──────────────────────────────────────────────────────

class TestRiskManagerRisk03:
    def test_check_stops_returns_none_when_no_position(self):
        """RISK-03: No position open → check_stops returns None."""
        rm = make_rm()
        assert rm.check_stops(make_market_state()) is None

    def test_check_stops_returns_none_above_stop_price(self):
        """RISK-03: Price above stop level → no exit signal."""
        rm = make_rm(stop_loss_pct=0.20)
        # Entry 0.50, stop = 0.40, current = 0.45 (above stop)
        rm.record_fill(make_order(fill_price=0.50, quantity=20.0), stop_loss_price=0.40)
        assert rm.check_stops(make_market_state(yes_price=0.45)) is None

    def test_check_stops_triggers_at_stop_price(self):
        """RISK-03: YES price hits stop_loss_price → SELL_YES exit signal returned."""
        rm = make_rm(stop_loss_pct=0.20)
        rm.record_fill(make_order(fill_price=0.50, quantity=20.0), stop_loss_price=0.40)
        signal = rm.check_stops(make_market_state(yes_price=0.40))
        assert signal is not None
        assert signal.direction == "SELL_YES"
        assert signal.confidence == 1.0

    def test_check_stops_triggers_below_stop_price(self):
        """RISK-03: YES price below stop_loss_price also triggers stop."""
        rm = make_rm()
        rm.record_fill(make_order(fill_price=0.50, quantity=20.0), stop_loss_price=0.40)
        signal = rm.check_stops(make_market_state(yes_price=0.35))
        assert signal is not None
        assert signal.direction == "SELL_YES"

    def test_check_stops_removes_position_after_trigger(self):
        """RISK-03: After stop-loss triggers, position is removed from tracking."""
        rm = make_rm()
        rm.record_fill(make_order(fill_price=0.50, quantity=20.0), stop_loss_price=0.40)
        rm.check_stops(make_market_state(yes_price=0.35))
        # Position should be gone — check_stops on next tick returns None
        assert rm.check_stops(make_market_state(yes_price=0.35)) is None

    def test_check_stops_no_side_for_no_position(self):
        """RISK-03: For a NO position, check against no_price, not yes_price."""
        rm = make_rm()
        # NO token bought at no_price=0.30 (yes_price was 0.70)
        # stop = 0.30 * (1 - 0.20) = 0.24
        order = make_order(side="NO", fill_price=0.30, quantity=33.0)
        rm.record_fill(order, stop_loss_price=0.24)
        # no_price = 1 - yes_price; yes_price=0.74 → no_price=0.26
        ms = make_market_state(yes_price=0.74)  # no_price = 0.26, below stop 0.24? No: 0.26 > 0.24
        assert rm.check_stops(ms) is None  # 0.26 > 0.24, no stop
        # Now yes_price=0.77 → no_price=0.23, below stop 0.24
        ms2 = make_market_state(yes_price=0.77)  # no_price=0.23 < 0.24
        signal = rm.check_stops(ms2)
        assert signal is not None
        assert signal.direction == "SELL_NO"


# ─── RISK-04: Cooldown Period ────────────────────────────────────────────────

class TestRiskManagerRisk04:
    def test_check_blocks_during_cooldown(self):
        """RISK-04: Within cooldown_seconds of last trade, check() returns False."""
        rm = make_rm(cooldown_seconds=300)
        # Record a fill then close it (trade completed)
        rm.record_fill(make_order(), stop_loss_price=0.40)
        rm.record_close("m1", exit_price=0.48)
        # Immediately try to re-enter same market — should be blocked
        assert rm.check(make_signal(), make_market_state()) is False

    def test_check_allows_after_cooldown_expires(self):
        """RISK-04: After cooldown expires, check() allows re-entry."""
        rm = make_rm(cooldown_seconds=300)
        # Set last_trade_time to 301 seconds ago
        past_time = datetime.now(timezone.utc) - timedelta(seconds=301)
        rm._last_trade_time["m1"] = past_time
        assert rm.check(make_signal(), make_market_state()) is True

    def test_cooldown_is_per_market(self):
        """RISK-04: Cooldown on m1 does not affect m2."""
        rm = make_rm(cooldown_seconds=300)
        rm.record_fill(make_order(market_id="m1"), stop_loss_price=0.40)
        rm.record_close("m1", exit_price=0.48)
        # m2 has no cooldown
        assert rm.check(make_signal(market_id="m2"), make_market_state(market_id="m2")) is True


# ─── RISK-05: Circuit Breakers ───────────────────────────────────────────────

class TestRiskManagerRisk05:
    def test_circuit_breaker_halts_at_5pct_drawdown(self):
        """RISK-05: -5% drawdown from peak triggers circuit breaker halt."""
        rm = make_rm(initial_capital=100.0)
        # Simulate $5.01 loss from $100 peak (> 5%)
        rm.record_fill(make_order(market_id="m1", fill_price=0.50, quantity=10.0), 0.10)
        rm.record_close("m1", exit_price=0.00)  # lose $5 (0.50 * 10 = $5)
        # Check at exactly -5%: portfolio = 95, drawdown = -5/100 = -5%
        # The test should trigger halt
        assert rm.is_halted is True

    def test_circuit_breaker_halts_at_10pct_drawdown(self):
        """RISK-05: -10% drawdown triggers circuit breaker."""
        rm = make_rm(initial_capital=100.0, daily_loss_limit=999.0)
        rm._portfolio_value = 89.0  # inject: 11% below peak of 100
        rm._peak_value = 100.0
        rm._update_drawdown()
        assert rm.is_halted is True

    def test_circuit_breaker_halts_at_15pct_drawdown(self):
        """RISK-05: -15% drawdown triggers circuit breaker."""
        rm = make_rm(initial_capital=100.0, daily_loss_limit=999.0)
        rm._portfolio_value = 84.0  # 16% below peak
        rm._peak_value = 100.0
        rm._update_drawdown()
        assert rm.is_halted is True

    def test_no_halt_below_5pct_drawdown(self):
        """RISK-05: Less than -5% drawdown does not trigger circuit breaker."""
        rm = make_rm(initial_capital=100.0, daily_loss_limit=999.0)
        rm._portfolio_value = 96.0  # 4% below peak, under threshold
        rm._peak_value = 100.0
        rm._update_drawdown()
        assert rm.is_halted is False

    def test_peak_updates_when_portfolio_rises(self):
        """Peak value is updated when portfolio exceeds previous peak."""
        rm = make_rm(initial_capital=100.0)
        rm._portfolio_value = 110.0
        rm._update_drawdown()
        assert rm._peak_value == 110.0

    def test_halted_blocks_all_subsequent_checks(self):
        """RISK-05: Once halted, check() always returns False regardless of market."""
        rm = make_rm(initial_capital=100.0, daily_loss_limit=999.0)
        rm._halted = True
        assert rm.check(make_signal("m1"), make_market_state("m1")) is False
        assert rm.check(make_signal("m2"), make_market_state("m2")) is False

    def test_circuit_breaker_levels_are_class_constants(self):
        """RISK-05: Breaker levels are hardcoded, not config-driven."""
        assert RiskManager.CIRCUIT_BREAKER_LEVELS == [-0.05, -0.10, -0.15]


# ─── record_fill ────────────────────────────────────────────────────────────

class TestRecordFill:
    def test_record_fill_creates_open_position(self):
        rm = make_rm()
        order = make_order(market_id="m1", fill_price=0.50, quantity=20.0)
        rm.record_fill(order, stop_loss_price=0.40)
        assert "m1" in rm._positions
        pos = rm._positions["m1"]
        assert isinstance(pos, OpenPosition)
        assert pos.entry_price == 0.50
        assert pos.quantity == 20.0
        assert pos.stop_loss_price == 0.40

    def test_record_fill_sets_last_trade_time(self):
        rm = make_rm()
        order = make_order()
        rm.record_fill(order, 0.40)
        assert "m1" in rm._last_trade_time
