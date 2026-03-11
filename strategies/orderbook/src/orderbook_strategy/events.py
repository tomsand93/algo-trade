"""Event types for orderbook backtesting."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class EventType(Enum):
    """Event types in the merged stream."""
    TRADE = "trade"
    BOOK_SNAPSHOT = "book_snapshot"
    HORIZON_READY = "horizon_ready"


class Side(Enum):
    """Order or trade side."""
    BUY = "buy"
    SELL = "sell"
    BID = "bid"
    ASK = "ask"


@dataclass
class Trade:
    """Trade event from tape."""
    timestamp: datetime
    price: float
    size: float
    side: Optional[Side] = None


@dataclass
class BookLevel:
    """Single orderbook level."""
    price: float
    size: float


@dataclass
class BookSnapshot:
    """Orderbook snapshot at a timestamp."""
    timestamp: datetime
    bids: list[BookLevel]
    asks: list[BookLevel]

    @property
    def best_bid(self) -> Optional[float]:
        """Best bid price."""
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        """Best ask price."""
        return self.asks[0].price if self.asks else None

    @property
    def mid(self) -> Optional[float]:
        """Mid price."""
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2


@dataclass
class HorizonEvent:
    """Event when a horizon return is ready for distribution update."""
    timestamp: datetime
    start_timestamp: datetime
    start_mid: float
    end_mid: float
    return_value: float
    state_key: str


Event = Trade | BookSnapshot | HorizonEvent
