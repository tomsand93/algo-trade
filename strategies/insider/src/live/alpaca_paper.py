"""
Alpaca paper trading integration.

Provides:
- Paper trading account connection
- Order submission with bracket orders
- Position monitoring
- Safety checks (paper-only enforcement)
"""
import os
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, List, Any
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class AlpacaOrder:
    """Alpaca order details."""
    symbol: str
    side: str  # "buy" or "sell"
    qty: Decimal
    order_type: str = "market"  # "market" or "limit"
    time_in_force: str = "day"
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None
    client_order_id: Optional[str] = None


@dataclass
class AlpacaPosition:
    """Alpaca position details."""
    symbol: str
    qty: Decimal
    avg_entry_price: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    side: str = "long"


class AlpacaPaperClient:
    """
    Client for Alpaca paper trading.

    Enforces paper-only trading with safety checks.
    """

    PAPER_BASE_URL = "https://paper-api.alpaca.markets"
    DATA_BASE_URL = "https://data.alpaca.markets"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ):
        """
        Initialize Alpaca paper client.

        Args:
            api_key: Alpaca API key (defaults to ALPACA_API_KEY env var)
            api_secret: Alpaca API secret (defaults to ALPACA_API_SECRET env var)
        """
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.api_secret = api_secret or os.getenv("ALPACA_API_SECRET")

        if not self.api_key or not self.api_secret:
            raise ValueError(
                "Alpaca credentials required. Set ALPACA_API_KEY and "
                "ALPACA_API_SECRET environment variables."
            )

        self.session = requests.Session()
        self.session.headers.update({
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
        })

        # Verify paper account
        self._verify_paper_account()

    def _verify_paper_account(self) -> None:
        """Verify that we're connected to a paper trading account."""
        try:
            self.get_account()
            # Check if this is a paper account
            # Alpaca doesn't explicitly mark paper accounts in API response,
            # but we verify by checking the base URL
            logger.info("Connected to Alpaca paper trading account")
        except Exception as e:
            logger.error(f"Failed to verify paper account: {e}")
            raise

    def _request(
        self,
        method: str,
        endpoint: str,
        base_url: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Make authenticated request to Alpaca API."""
        url = f"{base_url or self.PAPER_BASE_URL}/{endpoint}"
        response = self.session.request(method, url, timeout=30, **kwargs)
        response.raise_for_status()
        return response.json()

    def get_account(self) -> Dict[str, Any]:
        """Get account information."""
        return self._request("GET", "v2/account")

    def get_positions(self) -> List[AlpacaPosition]:
        """Get all open positions."""
        data = self._request("GET", "v2/positions")

        positions = []
        for p in data:
            qty = Decimal(p["qty"])
            # Handle short positions (negative qty)
            side = "short" if qty < 0 else "long"
            abs_qty = abs(qty)

            positions.append(AlpacaPosition(
                symbol=p["symbol"],
                qty=abs_qty,
                avg_entry_price=Decimal(p["avg_entry_price"]),
                current_price=Decimal(p["current_price"]),
                market_value=Decimal(p["market_value"]),
                unrealized_pnl=Decimal(p["unrealized_pl"]),
                side=side,
            ))

        return positions

    def submit_order(self, order: AlpacaOrder) -> Dict[str, Any]:
        """
        Submit an order to Alpaca.

        Args:
            order: AlpacaOrder object with order details

        Returns:
            Order confirmation from Alpaca
        """
        # Validate order
        if order.qty <= 0:
            raise ValueError(f"Invalid quantity: {order.qty}")

        payload = {
            "symbol": order.symbol,
            "qty": str(order.qty),
            "side": order.side,
            "type": order.order_type,
            "time_in_force": order.time_in_force,
        }

        # Add limit price if applicable
        if order.order_type == "limit" and order.limit_price:
            payload["limit_price"] = str(order.limit_price)

        # Add client order ID if provided
        if order.client_order_id:
            payload["client_order_id"] = order.client_order_id

        logger.info(f"Submitting order: {order.symbol} {order.side} {order.qty} shares")

        response = self._request("POST", "v2/orders", json=payload)

        logger.info(f"Order submitted: {response.get('id')}")

        return response

    def submit_bracket_order(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        stop_loss_pct: Decimal,
        take_profit_pct: Decimal,
    ) -> Dict[str, Any]:
        """
        Submit a bracket order with OCO stop-loss and take-profit.

        Args:
            symbol: Ticker symbol
            side: "buy" or "sell"
            qty: Quantity
            stop_loss_pct: Stop loss percentage (e.g., 0.08 for 8%)
            take_profit_pct: Take profit percentage (e.g., 0.16 for 16%)

        Returns:
            Order confirmation
        """
        # Get current price
        current_price = self.get_current_price(symbol)
        if current_price is None:
            raise ValueError(f"Cannot get current price for {symbol}")

        # Calculate stop and take prices
        if side == "buy":
            stop_loss_price = current_price * (Decimal("1") - stop_loss_pct)
            take_profit_price = current_price * (Decimal("1") + take_profit_pct)
            # For buy orders, set limit price slightly above current to ensure fill
            limit_price = current_price * (Decimal("1") + Decimal("0.01"))  # 1% above market
        else:
            stop_loss_price = current_price * (Decimal("1") + stop_loss_pct)
            take_profit_price = current_price * (Decimal("1") - take_profit_pct)
            # For sell orders, set limit price slightly below current to ensure fill
            limit_price = current_price * (Decimal("1") - Decimal("0.01"))  # 1% below market

        # Round to 2 decimal places (penny increments) for Alpaca
        quantize = Decimal("0.01")
        limit_price = limit_price.quantize(quantize)
        stop_loss_price = stop_loss_price.quantize(quantize)
        take_profit_price = take_profit_price.quantize(quantize)

        payload = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": "limit",  # Use limit instead of market for bracket orders
            "limit_price": str(limit_price),  # Set limit price
            "time_in_force": "day",
            "order_class": "bracket",
            "stop_loss": {
                "stop_price": str(stop_loss_price),
            },
            "take_profit": {
                "limit_price": str(take_profit_price),
            },
        }

        logger.info(
            f"Submitting bracket order: {symbol} {side} {qty} shares, "
            f"stop: ${float(stop_loss_price):.2f}, take: ${float(take_profit_price):.2f}"
        )

        response = self._request("POST", "v2/orders", json=payload)

        logger.info(f"Bracket order submitted: {response.get('id')}")

        return response

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order by ID."""
        try:
            self._request("DELETE", f"v2/orders/{order_id}")
            logger.info(f"Order {order_id} cancelled")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    def cancel_all_orders(self) -> int:
        """Cancel all open orders."""
        try:
            self._request("DELETE", "v2/orders")
            logger.info("All orders cancelled")
            return 0
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            return 0

    def get_orders(
        self,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get orders with optional status filter."""
        params = {"limit": limit}
        if status:
            params["status"] = status

        return self._request("GET", "v2/orders", params=params)

    def get_current_price(self, symbol: str) -> Optional[Decimal]:
        """Get current price for a symbol."""
        try:
            # Use Alpaca data API for latest trade
            data = self._request(
                "GET",
                f"v2/stocks/{symbol}/trades/latest",
                base_url=self.DATA_BASE_URL,
            )
            price = data.get("trade", {}).get("p")
            if price:
                return Decimal(str(price))
        except Exception as e:
            logger.warning(f"Failed to get price for {symbol}: {e}")

        return None

    def get_bars(
        self,
        symbol: str,
        timeframe: str = "1Day",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Get historical bars for a symbol.

        Args:
            symbol: Ticker symbol
            timeframe: Bar timeframe ("1Day", "1Hour", "15Min", etc.)
            start: Start datetime
            end: End datetime
            limit: Maximum number of bars

        Returns:
            List of bar dictionaries
        """
        params = {"timeframe": timeframe, "limit": limit}

        if start:
            params["start"] = start.isoformat()
        if end:
            params["end"] = end.isoformat()

        try:
            data = self._request(
                "GET",
                f"v2/stocks/{symbol}/bars",
                base_url=self.DATA_BASE_URL,
                params=params,
            )
            return data.get("bars", [])
        except Exception as e:
            logger.error(f"Failed to get bars for {symbol}: {e}")
            return []

    def close_position(self, symbol: str) -> Dict[str, Any]:
        """Close entire position for a symbol."""
        try:
            response = self._request("DELETE", f"v2/positions/{symbol}")
            logger.info(f"Closed position for {symbol}")
            return response
        except Exception as e:
            logger.error(f"Failed to close position for {symbol}: {e}")
            return {}

    def get_account_config(self) -> Dict[str, Any]:
        """Get account configuration for trading settings."""
        account = self.get_account()

        return {
            "buying_power": Decimal(account.get("buying_power", "0")),
            "cash": Decimal(account.get("cash", "0")),
            "portfolio_value": Decimal(account.get("portfolio_value", "0")),
            "daytrading_buying_power": Decimal(account.get("daytrading_buying_power", "0")),
            "regt_buying_power": Decimal(account.get("regt_buying_power", "0")),
            "multiplier": account.get("multiplier", 1),
        }


def validate_paper_mode() -> bool:
    """
    Validate that paper trading mode is enabled.

    Checks for PAPER_MODE environment variable.

    Returns:
        True if paper mode is confirmed
    """
    paper_mode = os.getenv("PAPER_MODE", "").lower() in ("true", "1", "yes")

    if not paper_mode:
        logger.error(
            "PAPER_MODE environment variable not set to 'true'. "
            "For safety, set PAPER_MODE=true before running paper trading."
        )
        return False

    return True
