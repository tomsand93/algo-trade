"""
Risk engine with 5 kill-switch rules.

Rules:
1. Daily Loss Stop: -10% realized PnL → disable 3 days
2. Rolling 14-Day DD: >15% → disable 5 days
3. Consecutive Losses: >=5 losing trades → disable 3 days
4. ATR Spike: ATR/close > p95 of 90-day window → suppress entries (soft)
5. DCA Stress: 3+ layer-4 round-trips in 14 days → disable 5 days

Disable means: cancel pending entries, prevent new entries, keep existing
exit orders. Shadow mode continues computing signals for recovery check.

Re-enable requires: cooldown expired + shadow trades >= 3 + positive
shadow expectancy. Reduced allocation (50%) for first 7 days after re-enable.
"""

from dataclasses import dataclass
from collections import deque
from datetime import datetime, timezone
from typing import Optional

from .models import TradeRecord


ACTIVE = 'active'
DISABLED = 'disabled'
COOLDOWN_COMPLETE = 'cooldown_complete'
RE_ENABLED = 're_enabled'

MS_PER_DAY = 24 * 3600 * 1000


@dataclass
class RiskConfig:
    # Daily loss stop
    daily_loss_threshold_pct: float = -10.0
    daily_loss_cooldown_days: int = 3

    # Rolling drawdown
    rolling_dd_threshold_pct: float = 15.0
    rolling_dd_window_days: int = 14
    rolling_dd_cooldown_days: int = 5

    # Consecutive losses
    max_consecutive_losses: int = 5
    consec_loss_cooldown_days: int = 3

    # ATR spike (soft bound)
    atr_spike_percentile: float = 95.0
    atr_spike_window_days: int = 90

    # DCA stress
    max_layer4_in_window: int = 3
    dca_stress_window_days: int = 14
    dca_stress_cooldown_days: int = 5

    # Re-enable
    shadow_min_trades: int = 3
    shadow_expectancy_window_days: int = 7
    reduced_allocation_days: int = 7
    reduced_allocation_pct: float = 50.0
    cooldown_extension_days: int = 3

    # Master switch
    enabled: bool = True


@dataclass
class KillSwitchEvent:
    timestamp_ms: int
    event_type: str       # 'disable' or 'enable'
    trigger_rule: str
    trigger_value: float
    threshold: float
    disabled_until_ms: Optional[int] = None


class RiskEngine:
    def __init__(self, config: RiskConfig):
        self.config = config

        # State machine
        self.state: str = ACTIVE
        self.disabled_until_ms: Optional[int] = None
        self.disable_reason: Optional[str] = None

        # ATR spike (soft, independent of state)
        self.entry_suppressed: bool = False
        self.suppress_reason: Optional[str] = None

        # Daily tracking
        self.day_start_equity: Optional[float] = None
        self.current_day_ms: Optional[int] = None
        self.daily_realized_pnl: float = 0.0

        # Consecutive losses
        self.consecutive_losses: int = 0

        # Equity history for rolling DD: (timestamp_ms, equity)
        self.equity_history: deque = deque()

        # ATR/close percentile history: (timestamp_ms, atr_pct)
        self.atr_pct_history: deque = deque()

        # Recent trades with exit timestamps: (timestamp_ms, TradeRecord)
        self.recent_trades: list = []

        # Shadow mode: trades that closed while disabled
        self.shadow_trades: list = []

        # Events log
        self.events: list = []

        # Re-enable reduced allocation tracking
        self.reduced_allocation_until_ms: Optional[int] = None

        # Track whether we just transitioned to disabled (for entry cancellation)
        self._just_disabled: bool = False

    def on_bar(self, timestamp_ms: int, equity: float,
               atr: Optional[float], close: float):
        """Called every bar to update risk state and check rules."""
        if not self.config.enabled:
            return

        self._just_disabled = False

        # Day boundary detection and reset
        day_ms = _day_start_ms(timestamp_ms)
        if self.current_day_ms is None or day_ms != self.current_day_ms:
            self.day_start_equity = equity
            self.daily_realized_pnl = 0.0
            self.current_day_ms = day_ms

        # Update equity history (rolling DD window)
        self.equity_history.append((timestamp_ms, equity))
        cutoff = timestamp_ms - self.config.rolling_dd_window_days * MS_PER_DAY
        while self.equity_history and self.equity_history[0][0] < cutoff:
            self.equity_history.popleft()

        # Update ATR/close history
        if atr is not None and close > 0:
            atr_pct = atr / close * 100
            self.atr_pct_history.append((timestamp_ms, atr_pct))
            cutoff_90d = timestamp_ms - self.config.atr_spike_window_days * MS_PER_DAY
            while self.atr_pct_history and self.atr_pct_history[0][0] < cutoff_90d:
                self.atr_pct_history.popleft()

        # Trim recent trades to 30 days (enough for any check)
        cutoff_30d = timestamp_ms - 30 * MS_PER_DAY
        self.recent_trades = [
            (ts, t) for ts, t in self.recent_trades if ts >= cutoff_30d
        ]

        # State machine transitions
        if self.state == ACTIVE:
            self._check_all_rules(timestamp_ms)
        elif self.state == DISABLED:
            if timestamp_ms >= self.disabled_until_ms:
                self.state = COOLDOWN_COMPLETE
                self._check_shadow_recovery(timestamp_ms)
        elif self.state == COOLDOWN_COMPLETE:
            self._check_shadow_recovery(timestamp_ms)
        elif self.state == RE_ENABLED:
            if (self.reduced_allocation_until_ms
                    and timestamp_ms >= self.reduced_allocation_until_ms):
                self.state = ACTIVE
                self.reduced_allocation_until_ms = None
            self._check_all_rules(timestamp_ms)

        # ATR spike check (always, independent of disable state)
        self._check_atr_spike(atr, close)

    def on_trade_closed(self, trade: TradeRecord, timestamp_ms: int):
        """Called when a round-trip trade closes."""
        self.recent_trades.append((timestamp_ms, trade))
        self.daily_realized_pnl += trade.pnl_net

        if trade.pnl_net < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        if self.state in (DISABLED, COOLDOWN_COMPLETE):
            self.shadow_trades.append(trade)

    def can_enter(self) -> bool:
        """Whether new entry orders are allowed."""
        if not self.config.enabled:
            return True
        if self.state in (DISABLED, COOLDOWN_COMPLETE):
            return False
        if self.entry_suppressed:
            return False
        return True

    def just_disabled(self) -> bool:
        """True on the bar where a disable just fired (for entry cancellation)."""
        return self._just_disabled

    def get_allocation_multiplier(self) -> float:
        """1.0 = full allocation, 0.5 = reduced (re-enabled state)."""
        if self.state == RE_ENABLED:
            return self.config.reduced_allocation_pct / 100.0
        return 1.0

    # ------ Rule checks ------

    def _check_all_rules(self, timestamp_ms: int):
        self._check_daily_loss(timestamp_ms)
        if self.state == DISABLED:
            return
        self._check_rolling_drawdown(timestamp_ms)
        if self.state == DISABLED:
            return
        self._check_consecutive_losses(timestamp_ms)
        if self.state == DISABLED:
            return
        self._check_dca_stress(timestamp_ms)

    def _check_daily_loss(self, timestamp_ms: int):
        if self.day_start_equity is None or self.day_start_equity <= 0:
            return
        pnl_pct = self.daily_realized_pnl / self.day_start_equity * 100
        if pnl_pct <= self.config.daily_loss_threshold_pct:
            self._disable(
                timestamp_ms,
                self.config.daily_loss_cooldown_days,
                f"daily_loss_{pnl_pct:.2f}pct",
                pnl_pct,
                self.config.daily_loss_threshold_pct,
            )

    def _check_rolling_drawdown(self, timestamp_ms: int):
        if len(self.equity_history) < 2:
            return
        peak = 0.0
        max_dd_pct = 0.0
        for _, eq in self.equity_history:
            if eq > peak:
                peak = eq
            if peak > 0:
                dd_pct = (peak - eq) / peak * 100
                if dd_pct > max_dd_pct:
                    max_dd_pct = dd_pct

        if max_dd_pct > self.config.rolling_dd_threshold_pct:
            self._disable(
                timestamp_ms,
                self.config.rolling_dd_cooldown_days,
                f"rolling_{self.config.rolling_dd_window_days}d_dd_{max_dd_pct:.2f}pct",
                max_dd_pct,
                self.config.rolling_dd_threshold_pct,
            )

    def _check_consecutive_losses(self, timestamp_ms: int):
        if self.consecutive_losses >= self.config.max_consecutive_losses:
            self._disable(
                timestamp_ms,
                self.config.consec_loss_cooldown_days,
                f"consec_losses_{self.consecutive_losses}",
                float(self.consecutive_losses),
                float(self.config.max_consecutive_losses),
            )

    def _check_atr_spike(self, atr: Optional[float], close: float):
        if atr is None or close <= 0:
            self.entry_suppressed = False
            return
        if len(self.atr_pct_history) < 100:
            self.entry_suppressed = False
            return

        current_atr_pct = atr / close * 100
        values = sorted(v for _, v in self.atr_pct_history)
        idx = int(len(values) * self.config.atr_spike_percentile / 100)
        idx = min(idx, len(values) - 1)
        p95 = values[idx]

        if current_atr_pct > p95:
            self.entry_suppressed = True
            self.suppress_reason = (
                f"atr_spike_{current_atr_pct:.4f}pct_vs_p95_{p95:.4f}pct"
            )
        else:
            self.entry_suppressed = False
            self.suppress_reason = None

    def _check_dca_stress(self, timestamp_ms: int):
        cutoff = timestamp_ms - self.config.dca_stress_window_days * MS_PER_DAY
        layer4_count = sum(
            1 for ts, t in self.recent_trades
            if ts >= cutoff and t.entry_id == 'entry4'
        )
        if layer4_count >= self.config.max_layer4_in_window:
            self._disable(
                timestamp_ms,
                self.config.dca_stress_cooldown_days,
                f"dca_stress_{layer4_count}_layer4_trips",
                float(layer4_count),
                float(self.config.max_layer4_in_window),
            )

    # ------ State transitions ------

    def _disable(self, timestamp_ms: int, cooldown_days: int,
                 reason: str, value: float, threshold: float):
        new_until = timestamp_ms + cooldown_days * MS_PER_DAY

        # If already disabled, only extend if new cooldown is longer
        if self.state == DISABLED and self.disabled_until_ms:
            if new_until <= self.disabled_until_ms:
                return

        self.state = DISABLED
        self.disabled_until_ms = new_until
        self.disable_reason = reason
        self.shadow_trades.clear()
        self._just_disabled = True

        self.events.append(KillSwitchEvent(
            timestamp_ms=timestamp_ms,
            event_type='disable',
            trigger_rule=reason,
            trigger_value=value,
            threshold=threshold,
            disabled_until_ms=new_until,
        ))

    def _check_shadow_recovery(self, timestamp_ms: int):
        if len(self.shadow_trades) < self.config.shadow_min_trades:
            # Not enough data, extend cooldown
            self.disabled_until_ms = (
                timestamp_ms + self.config.cooldown_extension_days * MS_PER_DAY
            )
            self.state = DISABLED
            return

        # Check shadow expectancy (positive total PnL)
        total_pnl = sum(t.pnl_net for t in self.shadow_trades)
        if total_pnl > 0:
            self.state = RE_ENABLED
            self.reduced_allocation_until_ms = (
                timestamp_ms + self.config.reduced_allocation_days * MS_PER_DAY
            )
            self.disable_reason = None

            self.events.append(KillSwitchEvent(
                timestamp_ms=timestamp_ms,
                event_type='enable',
                trigger_rule='shadow_recovery',
                trigger_value=total_pnl,
                threshold=0.0,
            ))
        else:
            # Negative expectancy, extend cooldown
            self.disabled_until_ms = (
                timestamp_ms + self.config.cooldown_extension_days * MS_PER_DAY
            )
            self.state = DISABLED


def _day_start_ms(timestamp_ms: int) -> int:
    """Get UTC midnight timestamp for the day containing timestamp_ms."""
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    day_start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(day_start.timestamp() * 1000)
