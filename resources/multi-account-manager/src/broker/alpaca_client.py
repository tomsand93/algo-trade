"""
Unified Alpaca broker client — PAPER ONLY.

Wraps alpaca-py TradingClient with paper=True enforced at construction.
Each account gets its own instance with its own API credentials.
"""

import logging
import time
from typing import Optional, List
from datetime import datetime, timezone, timedelta

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    GetOrdersRequest,
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
    StopLimitOrderRequest,
)
from alpaca.trading.enums import (
    OrderSide,
    OrderType,
    TimeInForce,
    QueryOrderStatus,
    OrderStatus,
)
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest, StockLatestBarRequest,
    CryptoBarsRequest, CryptoLatestBarRequest,
)
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from ..common.config import validate_paper_only, PAPER_BASE_URL

log = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF = 1.0


def _retry(func, *args, **kwargs):
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exc = e
            wait = RETRY_BACKOFF * (2 ** attempt)
            log.warning(
                "API call failed (attempt %d/%d): %s — retrying in %.1fs",
                attempt + 1, MAX_RETRIES, e, wait,
            )
            time.sleep(wait)
    raise last_exc


class PaperBroker:
    """
    Paper-only Alpaca broker.

    Enforces paper=True and blocks any live endpoint usage.
    """

    def __init__(self, api_key: str, api_secret: str, account_name: str = ""):
        validate_paper_only(PAPER_BASE_URL)
        self.account_name = account_name
        self.trading_client = TradingClient(
            api_key=api_key,
            secret_key=api_secret,
            paper=True,
        )
        self.data_client = StockHistoricalDataClient(
            api_key=api_key,
            secret_key=api_secret,
        )
        self.crypto_data_client = CryptoHistoricalDataClient(
            api_key=api_key,
            secret_key=api_secret,
        )
        log.info("[%s] PaperBroker initialized (paper=True)", account_name)

    # ---- Account ----

    def get_account(self):
        return _retry(self.trading_client.get_account)

    def get_equity(self) -> float:
        return float(self.get_account().equity)

    def get_cash(self) -> float:
        return float(self.get_account().cash)

    def get_buying_power(self) -> float:
        return float(self.get_account().buying_power)

    # ---- Positions ----

    def list_positions(self) -> list:
        return _retry(self.trading_client.get_all_positions)

    def get_position(self, symbol: str):
        """Get position for a symbol. Returns None if flat (no retry on 404)."""
        try:
            return self.trading_client.get_open_position(symbol)
        except Exception:
            return None

    def close_position(self, symbol: str):
        try:
            _retry(self.trading_client.close_position, symbol)
            log.info("[%s] Closed position: %s", self.account_name, symbol)
        except Exception as e:
            log.error("[%s] Failed to close %s: %s", self.account_name, symbol, e)

    # ---- Orders ----

    def submit_market_order(
        self, symbol: str, qty: float, side: str, time_in_force: str = "day"
    ):
        req = MarketOrderRequest(
            symbol=symbol,
            qty=round(qty, 4),
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY if time_in_force == "day" else TimeInForce.GTC,
        )
        order = _retry(self.trading_client.submit_order, req)
        log.info("[%s] Market %s %s qty=%.4f", self.account_name, side, symbol, qty)
        return order

    def submit_limit_order(
        self, symbol: str, qty: float, side: str,
        limit_price: float, time_in_force: str = "day"
    ):
        req = LimitOrderRequest(
            symbol=symbol,
            qty=round(qty, 4),
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            type=OrderType.LIMIT,
            time_in_force=TimeInForce.DAY if time_in_force == "day" else TimeInForce.GTC,
            limit_price=round(limit_price, 2),
        )
        order = _retry(self.trading_client.submit_order, req)
        log.info(
            "[%s] Limit %s %s qty=%.4f @ $%.2f",
            self.account_name, side, symbol, qty, limit_price,
        )
        return order

    def submit_stop_order(
        self, symbol: str, qty: float, side: str,
        stop_price: float, time_in_force: str = "day"
    ):
        req = StopOrderRequest(
            symbol=symbol,
            qty=round(qty, 4),
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            type=OrderType.STOP,
            time_in_force=TimeInForce.DAY if time_in_force == "day" else TimeInForce.GTC,
            stop_price=round(stop_price, 2),
        )
        order = _retry(self.trading_client.submit_order, req)
        log.info(
            "[%s] Stop %s %s qty=%.4f stop=$%.2f",
            self.account_name, side, symbol, qty, stop_price,
        )
        return order

    def cancel_order(self, order_id: str):
        _retry(self.trading_client.cancel_order_by_id, order_id)
        log.info("[%s] Cancelled order %s", self.account_name, order_id)

    def cancel_all_orders(self):
        _retry(self.trading_client.cancel_orders)
        log.info("[%s] Cancelled all orders", self.account_name)

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        req = GetOrdersRequest(
            status=QueryOrderStatus.OPEN,
            symbols=[symbol] if symbol else None,
        )
        return _retry(self.trading_client.get_orders, req)

    def get_closed_orders(
        self, since: Optional[datetime] = None, symbol: Optional[str] = None
    ) -> list:
        req = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
            after=since,
            symbols=[symbol] if symbol else None,
        )
        orders = _retry(self.trading_client.get_orders, req)
        return [o for o in orders if o.status == OrderStatus.FILLED]

    # ---- Market Data ----

    def get_latest_bar(self, symbol: str):
        req = StockLatestBarRequest(symbol_or_symbols=symbol)
        bars = _retry(self.data_client.get_stock_latest_bar, req)
        return bars.get(symbol)

    def get_bars(
        self, symbol: str, timeframe_minutes: int = 30,
        start: Optional[datetime] = None, limit: int = 200
    ):
        if start is None:
            start = datetime.now(timezone.utc) - timedelta(days=5)

        tf_map = {
            1: TimeFrame.Minute,
            5: TimeFrame(5, TimeFrameUnit.Minute),
            15: TimeFrame(15, TimeFrameUnit.Minute),
            30: TimeFrame(30, TimeFrameUnit.Minute),
            60: TimeFrame.Hour,
            240: TimeFrame(4, TimeFrameUnit.Hour),
            1440: TimeFrame.Day,
        }
        # NOTE: dict.get(key, default) always evaluates `default` eagerly.
        # TimeFrame(60, Minute) would raise ValueError, so use explicit lookup.
        tf = tf_map.get(timeframe_minutes) or TimeFrame(timeframe_minutes, TimeFrameUnit.Minute)

        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=tf,
            start=start,
            limit=limit,
        )
        barset = _retry(self.data_client.get_stock_bars, req)
        # BarSet.__contains__ is broken in this alpaca-py version (always returns False).
        # Use try/except on item access instead.
        try:
            return barset[symbol] or []
        except (KeyError, TypeError):
            return []

    # ---- Crypto Market Data ----

    def get_latest_crypto_bar(self, symbol: str):
        req = CryptoLatestBarRequest(symbol_or_symbols=symbol)
        bars = _retry(self.crypto_data_client.get_crypto_latest_bar, req)
        return bars.get(symbol)

    def get_crypto_bars(
        self, symbol: str, timeframe_minutes: int = 60,
        start: Optional[datetime] = None, limit: int = 200
    ):
        if start is None:
            start = datetime.now(timezone.utc) - timedelta(days=30)

        tf_map = {
            1: TimeFrame.Minute,
            5: TimeFrame(5, TimeFrameUnit.Minute),
            15: TimeFrame(15, TimeFrameUnit.Minute),
            30: TimeFrame(30, TimeFrameUnit.Minute),
            60: TimeFrame.Hour,
            240: TimeFrame(4, TimeFrameUnit.Hour),
            1440: TimeFrame.Day,
        }
        tf = tf_map.get(timeframe_minutes) or TimeFrame(timeframe_minutes, TimeFrameUnit.Minute)

        req = CryptoBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=tf,
            start=start,
            limit=limit,
        )
        barset = _retry(self.crypto_data_client.get_crypto_bars, req)
        try:
            return barset[symbol] or []
        except (KeyError, TypeError):
            return []

    # ---- Clock ----

    def get_clock(self):
        return _retry(self.trading_client.get_clock)

    def is_market_open(self) -> bool:
        try:
            clock = self.get_clock()
            return clock.is_open
        except Exception:
            return False
