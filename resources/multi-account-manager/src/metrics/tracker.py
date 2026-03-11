"""
Metrics tracker: per-account and combined metrics.

Collects equity snapshots, computes PnL, drawdown, win rate, and exposure.
All data is stored in-memory with periodic persistence to disk.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class EquitySnapshot:
    timestamp: str
    equity: float
    cash: float
    unrealized_pnl: float
    realized_pnl: float


@dataclass
class AccountMetrics:
    """Live metrics for a single account."""
    account_name: str
    initial_capital: float = 5000.0

    # Current state
    equity: float = 0.0
    cash: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

    # Daily tracking
    start_of_day_equity: float = 0.0
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0

    # Total tracking
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0

    # Trade stats
    trades_today: int = 0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0

    # Risk
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    peak_equity: float = 0.0
    exposure: float = 0.0  # % of capital in positions
    largest_position_value: float = 0.0
    position_count: int = 0

    # History
    equity_history: List[EquitySnapshot] = field(default_factory=list)
    daily_pnl_history: List[Dict] = field(default_factory=list)
    tracking_date: date = field(default_factory=date.today)

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades * 100

    def reset_daily(self, equity: float):
        """Reset daily counters for a new trading day."""
        # Save yesterday's daily PnL
        if self.tracking_date != date.today() and self.start_of_day_equity > 0:
            self.daily_pnl_history.append({
                "date": self.tracking_date.isoformat(),
                "pnl": self.daily_pnl,
                "pnl_pct": self.daily_pnl_pct,
                "equity": self.equity,
            })

        self.tracking_date = date.today()
        self.start_of_day_equity = equity
        self.daily_pnl = 0.0
        self.daily_pnl_pct = 0.0
        self.trades_today = 0

    def update(self, status: Dict):
        """Update metrics from a strategy status snapshot."""
        new_equity = status.get("equity", self.equity)
        # Skip update if equity is 0 — indicates a status error, not real equity
        if new_equity <= 0 and "error" in status:
            return
        # Also skip if equity is exactly 0 and we previously had a real value
        if new_equity <= 0 and self.equity > 0:
            return
        self.equity = new_equity
        self.cash = status.get("cash", self.cash)
        self.unrealized_pnl = status.get("unrealized_pnl", 0.0)
        self.realized_pnl = status.get("realized_pnl", self.realized_pnl)
        self.position_count = status.get("position_count", 0)
        self.trades_today = status.get("trades_today", self.trades_today)

        # Compute daily PnL
        if self.start_of_day_equity > 0:
            self.daily_pnl = self.equity - self.start_of_day_equity
            self.daily_pnl_pct = self.daily_pnl / self.start_of_day_equity * 100

        # Compute total PnL
        if self.initial_capital > 0:
            self.total_pnl = self.equity - self.initial_capital
            self.total_pnl_pct = self.total_pnl / self.initial_capital * 100

        # Track peak and drawdown
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity
        if self.peak_equity > 0:
            current_dd = (self.peak_equity - self.equity) / self.peak_equity * 100
            if current_dd > self.max_drawdown_pct:
                self.max_drawdown_pct = current_dd
                self.max_drawdown = self.peak_equity - self.equity

        # Exposure
        if self.equity > 0:
            invested = self.equity - self.cash
            self.exposure = max(0, invested / self.equity * 100)

        # Largest position
        positions = status.get("positions", [])
        if positions:
            self.largest_position_value = max(
                abs(p.get("market_value", 0)) for p in positions
            )
        else:
            self.largest_position_value = 0.0

        # Record equity snapshot
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.equity_history.append(EquitySnapshot(
            timestamp=now,
            equity=self.equity,
            cash=self.cash,
            unrealized_pnl=self.unrealized_pnl,
            realized_pnl=self.realized_pnl,
        ))

        # Trim history to last 2000 points to prevent memory bloat
        if len(self.equity_history) > 2000:
            self.equity_history = self.equity_history[-1500:]

    def to_dict(self) -> Dict:
        return {
            "account_name": self.account_name,
            "equity": self.equity,
            "cash": self.cash,
            "daily_pnl": self.daily_pnl,
            "daily_pnl_pct": self.daily_pnl_pct,
            "total_pnl": self.total_pnl,
            "total_pnl_pct": self.total_pnl_pct,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "trades_today": self.trades_today,
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "exposure": self.exposure,
            "largest_position_value": self.largest_position_value,
            "position_count": self.position_count,
        }


class MetricsTracker:
    """Tracks metrics for all accounts + combined totals."""

    def __init__(self, account_names: List[str], initial_capital: float = 5000.0):
        self.accounts: Dict[str, AccountMetrics] = {}
        for name in account_names:
            self.accounts[name] = AccountMetrics(
                account_name=name,
                initial_capital=initial_capital,
                equity=initial_capital,
                cash=initial_capital,
                peak_equity=initial_capital,
                start_of_day_equity=initial_capital,
            )

    def update_account(self, account_name: str, status: Dict):
        if account_name in self.accounts:
            metrics = self.accounts[account_name]

            # Check for new day
            if metrics.tracking_date != date.today():
                metrics.reset_daily(status.get("equity", metrics.equity))

            metrics.update(status)

    def get_account_metrics(self, account_name: str) -> Optional[AccountMetrics]:
        return self.accounts.get(account_name)

    def get_combined_metrics(self) -> Dict:
        """Compute combined metrics across all accounts."""
        total_equity = sum(m.equity for m in self.accounts.values())
        total_initial = sum(m.initial_capital for m in self.accounts.values())
        total_daily_pnl = sum(m.daily_pnl for m in self.accounts.values())
        total_pnl = total_equity - total_initial

        return {
            "total_equity": total_equity,
            "total_initial_capital": total_initial,
            "total_daily_pnl": total_daily_pnl,
            "total_daily_pnl_pct": (
                total_daily_pnl / total_initial * 100 if total_initial > 0 else 0
            ),
            "total_pnl": total_pnl,
            "total_pnl_pct": total_pnl / total_initial * 100 if total_initial > 0 else 0,
            "total_unrealized": sum(m.unrealized_pnl for m in self.accounts.values()),
            "total_realized": sum(m.realized_pnl for m in self.accounts.values()),
            "total_positions": sum(m.position_count for m in self.accounts.values()),
            "accounts": {
                name: m.to_dict() for name, m in self.accounts.items()
            },
        }

    def get_all_equity_histories(self) -> Dict[str, List[Dict]]:
        """Get equity history for all accounts (for charting)."""
        result = {}
        for name, m in self.accounts.items():
            result[name] = [
                {"timestamp": s.timestamp, "equity": s.equity}
                for s in m.equity_history
            ]
        return result

    def get_daily_pnl_histories(self) -> Dict[str, List[Dict]]:
        """Get daily PnL history for all accounts (for bar charts)."""
        return {
            name: m.daily_pnl_history for name, m in self.accounts.items()
        }
