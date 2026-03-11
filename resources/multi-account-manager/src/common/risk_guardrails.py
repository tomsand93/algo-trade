"""
Manager-level risk guardrails enforced on every account.

These are hard limits that override individual strategy decisions.
If a limit is breached, the bot for that account is paused.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

from .config import RiskLimits

log = logging.getLogger(__name__)


@dataclass
class AccountRiskState:
    """Tracks risk metrics for a single account within one trading day."""
    account_name: str
    start_of_day_equity: float
    current_equity: float = 0.0
    daily_pnl: float = 0.0
    orders_today: int = 0
    largest_position_value: float = 0.0
    is_halted: bool = False
    halt_reason: str = ""
    tracking_date: date = field(default_factory=date.today)

    def reset_for_new_day(self, equity: float):
        """Reset daily counters at start of new trading day."""
        self.tracking_date = date.today()
        self.start_of_day_equity = equity
        self.current_equity = equity
        self.daily_pnl = 0.0
        self.orders_today = 0
        self.largest_position_value = 0.0
        self.is_halted = False
        self.halt_reason = ""


def escalation_action(state: AccountRiskState, limits: RiskLimits) -> str:
    """
    Graduated risk escalation based on daily PnL and order count.

    Thresholds (% of daily loss limit):
      <50%  → allow     (normal trading)
      50-75% → warn     (log warning, keep trading)
      75-100% → reduce  (halve position sizes)
      >=100% → halt     (stop trading for the day)

    Order count uses a hard cutoff at the limit.
    """
    # --- Daily loss escalation ---
    if limits.max_daily_loss_usd > 0 and state.daily_pnl < 0:
        loss_ratio = abs(state.daily_pnl) / limits.max_daily_loss_usd

        if loss_ratio >= 1.0:
            return "halt"
        if loss_ratio >= 0.75:
            return "reduce"
        if loss_ratio >= 0.50:
            return "warn"

    # --- Order count hard cutoff ---
    if state.orders_today >= limits.max_orders_per_day:
        return "halt"

    return "allow"


class RiskGuardrail:
    """Enforces manager-level risk limits per account."""

    def __init__(self, limits: RiskLimits):
        self.limits = limits

    def check_new_day(self, state: AccountRiskState) -> bool:
        """Check if we've rolled into a new day and need a reset."""
        if state.tracking_date != date.today():
            return True
        return False

    def update_equity(self, state: AccountRiskState, current_equity: float):
        """Update equity and compute daily PnL."""
        state.current_equity = current_equity
        state.daily_pnl = current_equity - state.start_of_day_equity

    def check_order_allowed(self, state: AccountRiskState) -> bool:
        """Check if placing a new order is allowed under current limits."""
        if state.is_halted:
            return False

        action = escalation_action(state, self.limits)

        if action == "halt":
            state.is_halted = True
            state.halt_reason = (
                f"Risk escalation triggered: PnL=${state.daily_pnl:.2f}, "
                f"orders={state.orders_today}"
            )
            log.warning("[%s] HALTED: %s", state.account_name, state.halt_reason)
            return False

        if action == "reduce":
            log.warning(
                "[%s] RISK WARNING: approaching limits — reduced trading",
                state.account_name,
            )
            # Allow but the adapter should reduce size (checked downstream)
            state.largest_position_value = self.limits.max_position_value_usd * 0.5

        if action == "warn":
            log.info("[%s] Risk note: PnL=$%.2f, orders=%d",
                     state.account_name, state.daily_pnl, state.orders_today)

        return True

    def check_position_size(
        self, state: AccountRiskState, position_value_usd: float
    ) -> bool:
        """Check if a position size is within limits."""
        if position_value_usd > self.limits.max_position_value_usd:
            log.warning(
                "[%s] Position value $%.2f exceeds limit $%.2f — BLOCKED",
                state.account_name,
                position_value_usd,
                self.limits.max_position_value_usd,
            )
            return False
        return True

    def record_order(self, state: AccountRiskState):
        """Record that an order was placed."""
        state.orders_today += 1

    def to_dict(self, state: AccountRiskState) -> dict:
        """Serialize risk state for dashboard/reporting."""
        return {
            "account": state.account_name,
            "start_of_day_equity": state.start_of_day_equity,
            "current_equity": state.current_equity,
            "daily_pnl": state.daily_pnl,
            "daily_pnl_pct": (
                (state.daily_pnl / state.start_of_day_equity * 100)
                if state.start_of_day_equity > 0
                else 0.0
            ),
            "orders_today": state.orders_today,
            "is_halted": state.is_halted,
            "halt_reason": state.halt_reason,
            "limits": {
                "max_position_value_usd": self.limits.max_position_value_usd,
                "max_daily_loss_usd": self.limits.max_daily_loss_usd,
                "max_orders_per_day": self.limits.max_orders_per_day,
            },
        }
