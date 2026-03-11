"""
Unified Strategy Interface — all adapters must implement this.

Each adapter wraps an existing strategy repo without rewriting its logic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StrategyContext:
    """Shared context passed to every strategy lifecycle method."""
    account_name: str
    broker: Any  # PaperBroker instance
    initial_capital: float
    config: Dict[str, Any] = field(default_factory=dict)
    state: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyEvent:
    """An event emitted by a strategy for the dashboard event feed."""
    timestamp: str
    account: str
    event_type: str  # "signal", "order", "fill", "error", "info"
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


class BaseStrategy(ABC):
    """
    Unified interface that each strategy adapter must implement.

    Lifecycle:
        start(ctx)          -> called once at boot
        on_timer(ctx)       -> called every scan_interval
        on_order_update()   -> called when an order status changes
        stop(ctx)           -> called on shutdown
    """

    @abstractmethod
    async def start(self, ctx: StrategyContext) -> None:
        """Initialize strategy: warmup indicators, connect broker, etc."""
        ...

    @abstractmethod
    async def on_timer(self, ctx: StrategyContext) -> List[StrategyEvent]:
        """
        Periodic tick. Scan for setups, manage positions, etc.
        Returns a list of events for the dashboard feed.
        """
        ...

    async def on_market_data(self, ctx: StrategyContext, data: Any) -> List[StrategyEvent]:
        """Optional: handle streaming market data."""
        return []

    async def on_order_update(self, ctx: StrategyContext, update: Any) -> List[StrategyEvent]:
        """Handle order fill/cancel/reject events."""
        return []

    @abstractmethod
    async def stop(self, ctx: StrategyContext) -> None:
        """Graceful shutdown: cancel pending entries, save state."""
        ...

    @abstractmethod
    def get_status(self, ctx: StrategyContext) -> Dict[str, Any]:
        """
        Return current status snapshot for metrics/dashboard.
        Must include: equity, cash, positions, unrealized_pnl, realized_pnl
        """
        ...
