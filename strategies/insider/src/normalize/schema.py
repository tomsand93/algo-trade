"""
Data schemas for insider trading signals.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from enum import Enum


class TransactionCode(Enum):
    """SEC Form 4 transaction codes."""
    P = "P"  # Open market purchase
    S = "S"  # Open market sale


class TransactionType(Enum):
    """Acquisition or disposition."""
    ACQUISITION = "A"
    DISPOSITION = "D"


@dataclass(frozen=True)
class InsiderTransaction:
    """Normalized insider transaction from SEC Form 4."""
    ticker: str
    insider_name: str
    transaction_date: date
    filing_date: date
    transaction_code: str  # "P" for open-market purchase
    transaction_type: str  # "A" for acquisition
    shares: Decimal
    price_per_share: Optional[Decimal]
    total_value: Optional[Decimal]  # If provided directly
    filing_timestamp: Optional[datetime] = None  # Filing acceptance datetime

    @property
    def value_usd(self) -> Decimal:
        """Calculate transaction value in USD."""
        if self.total_value is not None:
            return self.total_value
        if self.price_per_share is not None and self.shares is not None:
            return self.price_per_share * self.shares
        return Decimal("0")

    @property
    def is_open_market_buy(self) -> bool:
        """Check if this is an open-market purchase (P code only)."""
        return (
            self.transaction_code == TransactionCode.P.value and
            self.transaction_type == TransactionType.ACQUISITION.value
        )

    @property
    def is_insider_buy(self) -> bool:
        """
        Check if this is an insider buy signal.

        Includes:
        - P: Open market purchases (most predictive)
        - M: Option exercises (insider chose to exercise)
        Both must be acquisitions (not dispositions).
        """
        return (
            self.transaction_code in ["P", "M"] and
            self.transaction_type == TransactionType.ACQUISITION.value
        )


@dataclass(frozen=True)
class InsiderSignal:
    """
    A trading signal based on a single insider buy event.
    Per spec: exactly ONE qualifying buy for ticker+date.
    """
    ticker: str
    signal_date: date  # Date signal becomes actionable
    transaction_date: date
    filing_date: date
    buy_value_usd: Decimal
    insider_name: str
    shares: Decimal
    price_per_share: Decimal

    def __post_init__(self):
        """Validate signal meets criteria."""
        if self.buy_value_usd <= 0:
            raise ValueError(f"Signal must have positive buy value: {self.buy_value_usd}")


@dataclass
class PriceBar:
    """OHLC price bar."""
    datetime: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    def to_dict(self) -> dict:
        return {
            "datetime": self.datetime.isoformat(),
            "open": float(self.open),
            "high": float(self.high),
            "low": float(self.low),
            "close": float(self.close),
            "volume": self.volume,
        }


@dataclass
class Fill:
    """Represent a trade fill with costs."""
    datetime: datetime
    ticker: str
    side: str  # "buy" or "sell"
    shares: Decimal
    price: Decimal
    commission: Decimal
    slippage_bps: Decimal

    @property
    def total_cost(self) -> Decimal:
        """Total cost including slippage."""
        slippage_factor = 1 + (self.slippage_bps / Decimal("10000"))
        if self.side == "buy":
            return self.shares * self.price * slippage_factor + self.commission
        else:
            return self.shares * self.price * slippage_factor - self.commission


@dataclass
class Position:
    """Open position in the portfolio."""
    ticker: str
    entry_date: date
    entry_price: Decimal
    shares: Decimal
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    entry_bar_index: int = 0
    highest_price: Optional[Decimal] = None  # For trailing stops

    def __post_init__(self):
        if self.highest_price is None:
            self.highest_price = self.entry_price

    @property
    def market_value(self, current_price: Decimal) -> Decimal:
        return self.shares * current_price

    @property
    def unrealized_pnl(self, current_price: Decimal) -> Decimal:
        return (current_price - self.entry_price) * self.shares


@dataclass
class TradeResult:
    """Result of a completed trade."""
    ticker: str
    entry_date: date
    exit_date: date
    entry_price: Decimal
    exit_price: Decimal
    shares: Decimal
    gross_pnl: Decimal
    costs: Decimal
    net_pnl: Decimal
    pnl_pct: Decimal
    hold_bars: int
    exit_reason: str  # "stop_loss", "take_profit", "time_exit", "max_hold", "force_close"

    @property
    def is_win(self) -> bool:
        return self.net_pnl > 0


@dataclass
class PortfolioSnapshot:
    """Portfolio state at a point in time."""
    date: date
    equity: Decimal
    cash: Decimal
    positions_value: Decimal
    n_positions: int
    drawdown: Decimal = Decimal("0")
