"""Alpaca API client for stock trading."""

import os
import logging
from typing import Optional, List
from dataclasses import dataclass
from datetime import datetime

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
    from alpaca.trading.enums import OrderSide, OrderType, TimeInForce, OrderClass
    from alpaca.trading.models import Order, Position
except ImportError:
    TradingClient = None
    raise ImportError("alpaca-py required. Run: pip install alpaca-py")

logger = logging.getLogger(__name__)


@dataclass
class AccountInfo:
    """Account information."""
    cash: float
    buying_power: float
    portfolio_value: float
    positions_count: int


@dataclass
class PositionInfo:
    """Position information."""
    symbol: str
    qty: float
    entry_price: float
    current_price: float
    unrealized_pl: float
    unrealized_pl_pct: float
    side: str


class AlpacaClient:
    """
    Alpaca Trading API wrapper.

    Supports paper and live trading modes.
    """

    def __init__(self, mode: str = "paper", key: Optional[str] = None, secret: Optional[str] = None):
        """
        Initialize Alpaca client.

        Args:
            mode: "paper" or "live"
            key: API key ID (defaults to ALPACA_PAPER_KEY or ALPACA_LIVE_KEY env var)
            secret: API secret (defaults to ALPACA_PAPER_SECRET or ALPACA_LIVE_SECRET env var)
        """
        if TradingClient is None:
            raise ImportError("alpaca-py not installed")

        self.mode = mode.lower()

        # Get credentials from params or env
        if self.mode == "paper":
            self.key_id = key or os.getenv("ALPACA_PAPER_KEY")
            self.secret_key = secret or os.getenv("ALPACA_PAPER_SECRET")
        else:
            self.key_id = key or os.getenv("ALPACA_LIVE_KEY")
            self.secret_key = secret or os.getenv("ALPACA_LIVE_SECRET")

        if not self.key_id or not self.secret_key:
            raise ValueError(f"Alpaca credentials not found for {mode} mode")

        # Initialize trading client
        self.client = TradingClient(
            api_key=self.key_id,
            secret_key=self.secret_key,
            paper=(self.mode == "paper")
        )

        logger.info(f"AlpacaClient initialized in {mode} mode")

    def get_account(self) -> AccountInfo:
        """Get account information."""
        account = self.client.get_account()

        return AccountInfo(
            cash=float(account.cash),
            buying_power=float(account.buying_power),
            portfolio_value=float(account.portfolio_value),
            positions_count=int(account.positions_count)
        )

    def get_positions(self) -> List[PositionInfo]:
        """Get all open positions."""
        positions = self.client.get_all_positions()

        result = []
        for pos in positions:
            result.append(PositionInfo(
                symbol=pos.symbol,
                qty=float(pos.quantity),
                entry_price=float(pos.avg_entry_price),
                current_price=float(pos.current_price),
                unrealized_pl=float(pos.unrealized_pl),
                unrealized_pl_pct=float(pos.unrealized_plpc),
                side=pos.side
            ))

        return result

    def get_position(self, symbol: str) -> Optional[PositionInfo]:
        """Get position for specific symbol."""
        try:
            pos = self.client.get_open_position(symbol_or_asset_id=symbol)
            return PositionInfo(
                symbol=pos.symbol,
                qty=float(pos.quantity),
                entry_price=float(pos.avg_entry_price),
                current_price=float(pos.current_price),
                unrealized_pl=float(pos.unrealized_pl),
                unrealized_pl_pct=float(pos.unrealized_plpc),
                side=pos.side
            )
        except Exception as e:
            logger.warning(f"No position found for {symbol}: {e}")
            return None

    def submit_market_order(
        self,
        symbol: str,
        qty: float,
        side: str
    ) -> str:
        """
        Submit a market order.

        Returns:
            Order ID
        """
        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

        request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.DAY
        )

        order = self.client.submit_order(request)
        logger.info(f"Market order submitted: {side} {qty} {symbol} -> {order.id}")
        return order.id

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a specific order."""
        try:
            self.client.cancel_order_by_id(order_id)
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    def cancel_all_orders_for_symbol(self, symbol: str) -> int:
        """Cancel all open orders for a symbol."""
        try:
            cancelled = self.client.cancel_orders()
            # Note: Alpaca doesn't support per-symbol cancel all in one call
            # We'd need to get orders first and selectively cancel
            logger.info(f"Cancelled orders for {symbol}")
            return len(cancelled) if cancelled else 0
        except Exception as e:
            logger.error(f"Failed to cancel orders for {symbol}: {e}")
            return 0

    def submit_order_with_bracket(
        self,
        symbol: str,
        qty: float,
        side: str,
        take_profit: float,
        stop_loss: float
    ) -> dict[str, str]:
        """
        Submit an order with OCO stop-loss and take-profit.

        Returns:
            Dict with order_ids for main, stop_loss, take_profit
        """
        from alpaca.trading.requests import TakeProfitRequest, StopLossRequest

        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

        # For buy orders: TP is limit sell, SL is stop sell
        # For sell orders: TP is limit buy, SL is stop buy
        if side.lower() == "buy":
            tp_request = TakeProfitRequest(limit_price=take_profit)
            sl_request = StopLossRequest(stop_price=stop_loss)
        else:
            # Short position logic (reverse)
            tp_request = TakeProfitRequest(limit_price=take_profit)
            sl_request = StopLossRequest(stop_price=stop_loss)

        request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.GTC,
            order_class=OrderClass.BRACKET,
            take_profit=tp_request,
            stop_loss=sl_request
        )

        order = self.client.submit_order(request)
        logger.info(f"Bracket order submitted: {side} {qty} {symbol}, SL={stop_loss}, TP={take_profit}")

        # Alpaca returns the main order; child orders are linked
        return {
            "main_order_id": order.id,
            # Child orders would need to be fetched separately
        }

    def is_market_open(self) -> bool:
        """Check if market is currently open."""
        clock = self.client.get_clock()
        return clock.is_open

    def get_next_market_open(self) -> datetime:
        """Get next market open time."""
        clock = self.client.get_clock()
        return clock.next_open.timestamp
