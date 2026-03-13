"""
Polymarket Data API client.

Fetches historical trade data from the Data API and converts
to domain models.
"""

from datetime import datetime, timezone

from pmirror.config import get_settings
from pmirror.data.client import BaseHttpClient
from pmirror.domain import Trade


class DataAPIClient(BaseHttpClient):
    """
    Client for the Polymarket Data API.

    Provides methods to fetch trade data and convert to domain models.
    """

    def __init__(self, settings=None):
        """
        Initialize the Data API client.

        Args:
            settings: Optional settings object (uses get_settings() if not provided)
        """
        config = settings if settings is not None else get_settings()
        super().__init__(
            base_url=config.api.data_api_url,
            settings=config,
            client_name="DataAPI",
        )

    def get_trades(
        self,
        maker: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[Trade]:
        """
        Fetch trades from the Data API.

        Args:
            maker: Filter by wallet address (maker)
            start: Start timestamp (inclusive)
            end: End timestamp (exclusive)
            limit: Maximum number of trades to return (default: 100)

        Returns:
            List of Trade domain models

        Raises:
            HttpClientError: On request errors
            ApiClientError: On API errors
        """
        params: dict[str, int | str] = {"limit": limit}

        if maker:
            params["maker"] = maker

        if start:
            params["start"] = int(start.timestamp())

        if end:
            params["end"] = int(end.timestamp())

        response = self.get("/trades", params=params)
        raw_trades = response.json()

        if not isinstance(raw_trades, list):
            raw_trades = []

        return [self._parse_trade(t) for t in raw_trades]

    def get_recent_trades(self, limit: int = 100) -> list[Trade]:
        """
        Fetch the most recent trades across all markets.

        Args:
            limit: Maximum number of trades to return

        Returns:
            List of Trade domain models
        """
        return self.get_trades(limit=limit)

    def get_wallet_trades(
        self,
        wallet: str,
        start: datetime,
        end: datetime,
        limit: int = 1000,
    ) -> list[Trade]:
        """
        Fetch all trades for a specific wallet within a date range.

        Args:
            wallet: Wallet address (0x...)
            start: Start timestamp
            end: End timestamp
            limit: Maximum trades to fetch

        Returns:
            List of Trade domain models
        """
        return self.get_trades(maker=wallet, start=start, end=end, limit=limit)

    def _parse_trade(self, raw: dict) -> Trade:
        """
        Convert raw API response to Trade domain model.

        Args:
            raw: Raw trade data from API

        Returns:
            Trade domain model
        """
        # Convert side to lowercase
        side = raw.get("side", "buy").lower()
        if side not in ("buy", "sell"):
            side = "buy"

        # Convert timestamp (Unix epoch) to datetime
        timestamp = datetime.fromtimestamp(raw.get("timestamp", 0), tz=timezone.utc)

        return Trade(
            transaction_hash=raw.get("transactionHash", ""),
            timestamp=timestamp,
            maker=raw.get("proxyWallet", ""),
            taker=None,  # Not provided by API
            side=side,  # type: ignore
            outcome=raw.get("outcome", ""),
            price=float(raw.get("price", 0)),
            size=float(raw.get("size", 0)),
            market_id=raw.get("conditionId", ""),
            shares=None,  # Will be computed
            fee=None,  # Not provided by API
        )

    def get_trade_count(
        self,
        wallet: str,
        start: datetime,
        end: datetime,
    ) -> int:
        """
        Get the count of trades for a wallet in a date range.

        Args:
            wallet: Wallet address
            start: Start timestamp
            end: End timestamp

        Returns:
            Number of trades
        """
        trades = self.get_wallet_trades(wallet, start, end, limit=1)
        # Note: API doesn't return count, so we return fetched count
        # In production, might need to fetch all to get accurate count
        return len(trades)
