"""
Alpaca API wrapper for paper trading.

Uses alpaca-py SDK with paper=True. API keys from env vars:
  ALPACA_API_KEY, ALPACA_API_SECRET

Provides methods for account info, positions, and order management.
Stop entries use stop-limit with a price buffer (Alpaca crypto requirement).
All API calls wrapped in retry logic (3 attempts, exponential backoff).
"""

import os
import time
import logging
from typing import Optional
from datetime import datetime, timezone, timedelta

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
    StopLimitOrderRequest,
    StopOrderRequest,
    ReplaceOrderRequest,
)
from alpaca.trading.enums import (
    OrderSide,
    OrderType,
    TimeInForce,
    OrderStatus,
    QueryOrderStatus,
)

log = logging.getLogger(__name__)

# Buffer above stop price for the limit portion of stop-limit orders.
# Alpaca crypto requires stop-limit (not plain stop). The limit is set
# this percentage above the stop to ensure fills in fast markets.
STOP_LIMIT_BUFFER_PCT = 2.5

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 1.0  # seconds


def _retry(func, *args, **kwargs):
    """Call func with retry logic. Returns result or raises last exception."""
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exc = e
            wait = RETRY_BACKOFF_BASE * (2 ** attempt)
            log.warning("API call %s failed (attempt %d/%d): %s — retrying in %.1fs",
                        func.__name__ if hasattr(func, '__name__') else func,
                        attempt + 1, MAX_RETRIES, e, wait)
            time.sleep(wait)
    raise last_exc


class AlpacaBroker:
    """Thin wrapper around Alpaca TradingClient for BDB DCA bot."""

    def __init__(self, api_key: Optional[str] = None,
                 api_secret: Optional[str] = None):
        self.api_key = api_key or os.environ["ALPACA_API_KEY"]
        self.api_secret = api_secret or os.environ["ALPACA_API_SECRET"]
        self.client: Optional[TradingClient] = None

    def connect(self):
        """Initialize the TradingClient (paper mode)."""
        self.client = TradingClient(
            api_key=self.api_key,
            secret_key=self.api_secret,
            paper=True,
        )
        acct = _retry(self.client.get_account)
        log.info("Connected to Alpaca paper account: equity=$%s, cash=$%s",
                 acct.equity, acct.cash)
        return acct

    # ---- Account info ----

    def get_account(self):
        """Return full Alpaca account object."""
        return _retry(self.client.get_account)

    def get_equity(self) -> float:
        acct = self.get_account()
        return float(acct.equity)

    def get_cash(self) -> float:
        acct = self.get_account()
        return float(acct.cash)

    def get_btc_position(self):
        """Return BTC/USD position or None if flat."""
        try:
            pos = _retry(self.client.get_open_position, "BTC/USD")
            return pos
        except Exception:
            return None

    def get_stock_position(self, symbol: str):
        """Return stock position or None if flat.

        Args:
            symbol: Stock symbol (e.g. "AAPL")
        """
        try:
            pos = _retry(self.client.get_open_position, symbol)
            return pos
        except Exception:
            return None

    # ---- Orders ----

    def place_stop_limit_buy(self, symbol: str, qty: float,
                             stop_price: float,
                             client_order_id: Optional[str] = None):
        """Place a stop-limit buy order.

        The limit price is set STOP_LIMIT_BUFFER_PCT above the stop price
        to account for slippage while still acting as a stop entry.
        """
        limit_price = round(stop_price * (1 + STOP_LIMIT_BUFFER_PCT / 100), 2)
        req = StopLimitOrderRequest(
            symbol=symbol,
            qty=round(qty, 8),
            side=OrderSide.BUY,
            type=OrderType.STOP_LIMIT,
            time_in_force=TimeInForce.GTC,
            stop_price=round(stop_price, 2),
            limit_price=limit_price,
            client_order_id=client_order_id,
        )
        order = _retry(self.client.submit_order, req)
        log.info("Placed stop-limit BUY: %s qty=%.8f stop=$%.2f limit=$%.2f id=%s",
                 symbol, qty, stop_price, limit_price, order.id)
        return order

    def place_limit_sell(self, symbol: str, qty: float,
                         limit_price: float,
                         client_order_id: Optional[str] = None):
        """Place a limit sell (take-profit exit)."""
        req = LimitOrderRequest(
            symbol=symbol,
            qty=round(qty, 8),
            side=OrderSide.SELL,
            type=OrderType.LIMIT,
            time_in_force=TimeInForce.GTC,
            limit_price=round(limit_price, 2),
            client_order_id=client_order_id,
        )
        order = _retry(self.client.submit_order, req)
        log.info("Placed limit SELL: %s qty=%.8f limit=$%.2f id=%s",
                 symbol, qty, limit_price, order.id)
        return order

    def cancel_order(self, order_id: str):
        """Cancel a single order by Alpaca order ID."""
        _retry(self.client.cancel_order_by_id, order_id)
        log.info("Cancelled order %s", order_id)

    def replace_order(self, order_id: str, qty: Optional[float] = None,
                      limit_price: Optional[float] = None,
                      stop_price: Optional[float] = None):
        """Replace (amend) an existing order's price/qty."""
        params = {}
        if qty is not None:
            params["qty"] = round(qty, 8)
        if limit_price is not None:
            params["limit_price"] = round(limit_price, 2)
        if stop_price is not None:
            params["stop_price"] = round(stop_price, 2)
        req = ReplaceOrderRequest(**params)
        order = _retry(self.client.replace_order_by_id, order_id, req)
        log.info("Replaced order %s: %s", order_id, params)
        return order

    def get_open_orders(self, symbol: Optional[str] = None):
        """Return list of open orders, optionally filtered by symbol."""
        req = GetOrdersRequest(
            status=QueryOrderStatus.OPEN,
            symbols=[symbol] if symbol else None,
        )
        return _retry(self.client.get_orders, req)

    def get_filled_orders_since(self, since: datetime,
                                symbol: Optional[str] = None):
        """Return orders filled since a given datetime."""
        req = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
            after=since,
            symbols=[symbol] if symbol else None,
        )
        orders = _retry(self.client.get_orders, req)
        return [o for o in orders if o.status == OrderStatus.FILLED]

    # ---- Emergency ----

    def close_position(self, symbol: str):
        """Market-close the entire position for a symbol."""
        try:
            _retry(self.client.close_position, symbol)
            log.warning("Emergency close position: %s", symbol)
        except Exception as e:
            log.error("Failed to close position %s: %s", symbol, e)

    def cancel_all_orders(self):
        """Cancel all open orders."""
        _retry(self.client.cancel_orders)
        log.warning("Cancelled ALL open orders")

    # ---- Stock-specific orders ----

    def place_stop_buy(self, symbol: str, qty: float,
                       stop_price: float,
                       client_order_id: Optional[str] = None):
        """Place a plain stop buy order for stocks.

        Unlike crypto, stocks support plain STOP orders (no limit required).
        """
        req = StopOrderRequest(
            symbol=symbol,
            qty=round(qty, 4),  # Stocks use fewer decimal places
            side=OrderSide.BUY,
            type=OrderType.STOP,
            time_in_force=TimeInForce.DAY,  # Stock orders typically use DAY
            stop_price=round(stop_price, 2),
            client_order_id=client_order_id,
        )
        order = _retry(self.client.submit_order, req)
        log.info("Placed stop BUY: %s qty=%.4f stop=$%.2f id=%s",
                 symbol, qty, stop_price, order.id)
        return order

    def place_market_sell(self, symbol: str, qty: float,
                          client_order_id: Optional[str] = None):
        """Place a market sell order for emergency exits."""
        req = MarketOrderRequest(
            symbol=symbol,
            qty=round(qty, 4),
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
            client_order_id=client_order_id,
        )
        order = _retry(self.client.submit_order, req)
        log.info("Placed market SELL: %s qty=%.4f id=%s",
                 symbol, qty, order.id)
        return order
