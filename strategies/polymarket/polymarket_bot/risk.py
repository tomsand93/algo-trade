"""Risk management for the Polymarket trading bot.

RiskManager enforces all risk controls before any order is placed and
monitors open positions for stop-loss conditions on every tick.

Risk controls implemented:
  RISK-01: Max one position per market (no averaging in)
  RISK-02: Daily loss limit halts all trading when breached
  RISK-03: Per-position stop-loss triggers automatic exit signal
  RISK-04: Cooldown period prevents rapid re-entry per market
  RISK-05: Circuit breakers halt at -5%/-10%/-15% drawdown from peak

Call sequence in run_loop():
  1. risk_manager.check_stops(market_state)  → exit if stop hit
  2. strategy.generate_signal(market_state)  → entry signal candidate
  3. strategy.should_trade(signal, ...)      → confidence pre-filter
  4. risk_manager.check(signal, market_state)→ risk gate (blocks if unsafe)
  5. simulate_order(signal, ...)             → paper order
  6. risk_manager.record_fill(order, stop)   → update positions state

Phase 2: no persistence — all state is in-memory, ephemeral per run.
Phase 4 will add disk persistence via record_close() and reset_daily() scheduling.
"""
from datetime import datetime, timezone
from loguru import logger

from polymarket_bot.models import MarketState, OpenPosition, Signal, SimulatedOrder


class RiskManager:
    """Stateful risk gatekeeper for the trading bot.

    State:
      _positions:       {market_id: OpenPosition} — currently open positions
      _daily_pnl:       float — cumulative realized PnL since last reset (USD)
      _portfolio_value: float — current estimated portfolio value
      _peak_value:      float — highest portfolio value seen since bot start
      _last_trade_time: {market_id: datetime} — UTC timestamp of last fill per market
      _halted:          bool — True once any circuit breaker fires
      _halt_reason:     str — human-readable reason for halt
    """

    CIRCUIT_BREAKER_LEVELS = [-0.05, -0.10, -0.15]

    def __init__(
        self,
        initial_capital: float,
        max_position_size: float,
        daily_loss_limit: float,
        stop_loss_pct: float,
        cooldown_seconds: int,
    ) -> None:
        self.initial_capital = initial_capital
        self.max_position_size = max_position_size
        self.daily_loss_limit = daily_loss_limit
        self.stop_loss_pct = stop_loss_pct
        self.cooldown_seconds = cooldown_seconds

        self._positions: dict[str, OpenPosition] = {}
        self._daily_pnl: float = 0.0
        self._portfolio_value: float = initial_capital
        self._peak_value: float = initial_capital
        self._last_trade_time: dict[str, datetime] = {}
        self._halted: bool = False
        self._halt_reason: str = ""

    # ── Public Properties ──────────────────────────────────────────────────

    @property
    def is_halted(self) -> bool:
        """True if any circuit breaker or loss limit has fired."""
        return self._halted

    # ── Risk Gate ──────────────────────────────────────────────────────────

    def check(self, signal: Signal, market_state: MarketState) -> bool:
        """Return True if the signal is safe to act on.

        Checks in order (cheapest first):
          1. Global halt (circuit breaker or daily loss already fired)
          2. RISK-01: No existing position in this market
          3. RISK-02: Daily loss limit not breached
          4. RISK-04: Cooldown period expired
        """
        # Check 1: Global halt
        if self._halted:
            return False

        # Check 2 (RISK-01): Only one position per market
        if market_state.market_id in self._positions:
            return False

        # Check 3 (RISK-02): Daily loss limit
        if abs(self._daily_pnl) >= self.daily_loss_limit:
            self._halt(f"Daily loss limit breached: pnl={self._daily_pnl:.2f} >= limit={self.daily_loss_limit:.2f}")
            return False

        # Check 4 (RISK-04): Cooldown period
        if self._is_in_cooldown(market_state.market_id):
            return False

        return True

    # ── Stop-Loss Monitoring ───────────────────────────────────────────────

    def check_stops(self, market_state: MarketState) -> Signal | None:
        """Check if any open position in this market has hit its stop-loss.

        Returns a SELL_YES or SELL_NO exit Signal if stop triggered, else None.
        Updates daily_pnl and portfolio_value on exit. Removes position.
        """
        pos = self._positions.get(market_state.market_id)
        if pos is None:
            return None

        # Use yes_price for YES positions, no_price for NO positions (RISK-03 pitfall 4)
        current_price = (
            market_state.yes_price if pos.side == "YES" else market_state.no_price
        )

        if current_price <= pos.stop_loss_price:
            exit_direction = "SELL_YES" if pos.side == "YES" else "SELL_NO"
            loss = round((current_price - pos.entry_price) * pos.quantity, 4)
            self._daily_pnl = round(self._daily_pnl + loss, 4)
            self._portfolio_value = round(self._portfolio_value + loss, 4)
            self._update_drawdown()
            del self._positions[market_state.market_id]
            logger.warning(
                "STOP-LOSS | market={market} | side={side} | "
                "entry={entry:.4f} | current={curr:.4f} | stop={stop:.4f} | pnl={pnl:.4f}",
                market=market_state.market_id,
                side=pos.side,
                entry=pos.entry_price,
                curr=current_price,
                stop=pos.stop_loss_price,
                pnl=loss,
            )
            return Signal(
                market_id=market_state.market_id,
                direction=exit_direction,
                confidence=1.0,
                price=current_price,
                reason=(
                    f"Stop-loss triggered: {current_price:.4f} <= {pos.stop_loss_price:.4f} "
                    f"(entry={pos.entry_price:.4f}, pnl={loss:.4f})"
                ),
            )
        return None

    # ── State Mutators ─────────────────────────────────────────────────────

    def record_fill(self, order: SimulatedOrder, stop_loss_price: float) -> None:
        """Record a simulated order fill and open the position.

        Must be called immediately after every order is executed.
        stop_loss_price should be pre-computed: fill_price * (1 - stop_loss_pct)
        """
        pos = OpenPosition(
            market_id=order.market_id,
            side=order.side,
            direction=order.direction,
            entry_price=order.fill_price,
            quantity=order.quantity,
            stop_loss_price=stop_loss_price,
            opened_at=order.timestamp,
        )
        self._positions[order.market_id] = pos
        self._last_trade_time[order.market_id] = order.timestamp
        logger.info(
            "POSITION OPENED | market={market} | side={side} | "
            "entry={entry:.4f} | qty={qty:.4f} | stop={stop:.4f}",
            market=order.market_id,
            side=order.side,
            entry=order.fill_price,
            qty=order.quantity,
            stop=stop_loss_price,
        )

    def record_close(self, market_id: str, exit_price: float) -> None:
        """Record a non-stop-loss position close and update PnL.

        Used for take-profit or manual exit (Phase 3+).
        """
        pos = self._positions.pop(market_id, None)
        if pos is None:
            return
        pnl = round((exit_price - pos.entry_price) * pos.quantity, 4)
        self._daily_pnl = round(self._daily_pnl + pnl, 4)
        self._portfolio_value = round(self._portfolio_value + pnl, 4)
        self._update_drawdown()
        logger.info(
            "POSITION CLOSED | market={market} | exit={exit:.4f} | pnl={pnl:.4f} | "
            "daily_pnl={daily:.4f}",
            market=market_id,
            exit=exit_price,
            pnl=pnl,
            daily=self._daily_pnl,
        )

    def reset_daily(self) -> None:
        """Reset daily PnL counter for a new trading day.

        NOTE: Does NOT reset _peak_value — circuit breakers track all-time drawdown.
        NOTE: Does NOT unhalted the manager — only a manual restart clears halt state.
        Phase 4 will wire this to a scheduler (daily at market open).
        """
        self._daily_pnl = 0.0
        logger.info("DAILY RESET | daily_pnl reset to 0.0 | peak_value={peak:.2f}", peak=self._peak_value)

    # ── Internal Helpers ───────────────────────────────────────────────────

    def _is_in_cooldown(self, market_id: str) -> bool:
        """Return True if the market is within the cooldown period."""
        last = self._last_trade_time.get(market_id)
        if last is None:
            return False
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        return elapsed < self.cooldown_seconds

    def _update_drawdown(self) -> None:
        """Update peak value and check circuit breakers after every PnL change.

        Circuit breaker levels are hardcoded as class constants (not config)
        because they are safety invariants, not tunable parameters.
        """
        if self._portfolio_value > self._peak_value:
            self._peak_value = self._portfolio_value
            return

        drawdown = (self._portfolio_value - self._peak_value) / self._peak_value
        for level in self.CIRCUIT_BREAKER_LEVELS:
            if drawdown <= level:
                self._halt(
                    f"Circuit breaker: drawdown={drawdown:.1%} hit level={level:.0%}"
                )
                return

    def _halt(self, reason: str) -> None:
        """Engage the halt flag and log the reason. All subsequent check() calls return False."""
        self._halted = True
        self._halt_reason = reason
        logger.critical("TRADING HALTED | reason={reason}", reason=reason)
