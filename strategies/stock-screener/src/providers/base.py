"""Abstract base classes for data providers."""

from abc import ABC, abstractmethod
from typing import Any, Optional
from dataclasses import dataclass


@dataclass
class PriceData:
    """Price and technical data for a ticker."""
    symbol: str
    price: float
    change: float
    change_pct: float
    volume: Optional[int] = None
    rsi_14: Optional[float] = None
    ma50: Optional[float] = None
    ma200: Optional[float] = None
    atr: Optional[float] = None


@dataclass
class FundamentalData:
    """Fundamental data for a ticker."""
    symbol: str
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    revenue_growth: Optional[float] = None
    eps_growth: Optional[float] = None
    debt_to_equity: Optional[float] = None
    roe: Optional[float] = None
    eps: Optional[float] = None


@dataclass
class NewsHeadline:
    """News headline with sentiment."""
    title: str
    source: str
    url: str
    published_at: str
    sentiment: Optional[float] = None  # -1 to 1


class PriceProvider(ABC):
    """Abstract base for price/technical data providers."""

    @abstractmethod
    async def get_price(self, symbol: str) -> Optional[PriceData]:
        """Fetch current price and technicals for a symbol."""
        pass

    @abstractmethod
    async def get_prices_batch(self, symbols: list[str]) -> dict[str, PriceData]:
        """Fetch prices for multiple symbols."""
        pass


class FundamentalProvider(ABC):
    """Abstract base for fundamental data providers."""

    @abstractmethod
    async def get_fundamentals(self, symbol: str) -> Optional[FundamentalData]:
        """Fetch fundamental data for a symbol."""
        pass

    @abstractmethod
    async def get_fundamentals_batch(self, symbols: list[str]) -> dict[str, FundamentalData]:
        """Fetch fundamentals for multiple symbols."""
        pass


class NewsProvider(ABC):
    """Abstract base for news providers."""

    @abstractmethod
    async def get_news(self, symbol: str, days_back: int = 7, limit: int = 5) -> list[NewsHeadline]:
        """Fetch recent news for a symbol."""
        pass
