from dataclasses import dataclass, field
from typing import Optional
import math


@dataclass
class Bar:
    timestamp: int          # milliseconds
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def hl2(self) -> float:
        return (self.high + self.low) / 2.0


@dataclass
class PendingOrder:
    """A pending stop-entry or limit-exit order."""
    order_id: str           # e.g. 'entry1', 'exit_entry1'
    direction: str          # 'long'
    order_type: str         # 'stop' for entries, 'limit' for exits
    price: float
    qty: float
    from_entry: Optional[str] = None  # for exit orders, which entry they close


@dataclass
class Fill:
    """A single entry fill in the position."""
    entry_id: str
    fill_bar_index: int
    fill_price: float
    qty: float
    commission: float


@dataclass
class TradeRecord:
    """A completed round-trip trade (entry + exit)."""
    entry_id: str
    entry_bar_index: int
    entry_price: float
    entry_qty: float
    exit_bar_index: int
    exit_price: float
    pnl_gross: float       # (exit_price - entry_price) * qty
    commission_total: float # entry + exit commission
    pnl_net: float          # pnl_gross - commission_total


@dataclass
class BacktestResult:
    trades: list            # list of TradeRecord
    final_equity: float
    initial_capital: float
    peak_equity: float
    max_drawdown: float     # peak-to-trough mark-to-market drawdown
    equity_curve: list      # list of (timestamp, equity) tuples

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def winning_trades(self) -> int:
        return sum(1 for t in self.trades if t.pnl_net > 0)

    @property
    def losing_trades(self) -> int:
        return sum(1 for t in self.trades if t.pnl_net <= 0)

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades * 100.0

    @property
    def net_profit(self) -> float:
        return self.final_equity - self.initial_capital

    @property
    def net_profit_pct(self) -> float:
        return self.net_profit / self.initial_capital * 100.0

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t.pnl_net for t in self.trades if t.pnl_net > 0)
        gross_loss = abs(sum(t.pnl_net for t in self.trades if t.pnl_net <= 0))
        if gross_loss == 0:
            return float('inf')
        return gross_profit / gross_loss

    @property
    def avg_trade_pnl(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return sum(t.pnl_net for t in self.trades) / self.total_trades

    @property
    def closed_trade_max_drawdown(self) -> float:
        """Max drawdown computed on closed-trade equity only (Pine's method).
        This is the peak-to-trough of cumulative realized PnL."""
        cum_pnl = 0.0
        peak_pnl = 0.0
        max_dd = 0.0
        for t in self.trades:
            cum_pnl += t.pnl_net
            if cum_pnl > peak_pnl:
                peak_pnl = cum_pnl
            dd = peak_pnl - cum_pnl
            if dd > max_dd:
                max_dd = dd
        return max_dd
