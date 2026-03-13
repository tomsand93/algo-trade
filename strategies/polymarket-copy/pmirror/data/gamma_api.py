"""
Polymarket Gamma API client.

Fetches market metadata from the Gamma API and converts
to domain models.
"""

import json
from datetime import datetime, timezone

from pmirror.config import get_settings
from pmirror.data.client import BaseHttpClient
from pmirror.domain import Market


class GammaAPIClient(BaseHttpClient):
    """
    Client for the Polymarket Gamma API.

    Provides methods to fetch market data and convert to domain models.
    """

    def __init__(self, settings=None):
        """
        Initialize the Gamma API client.

        Args:
            settings: Optional settings object (uses get_settings() if not provided)
        """
        config = settings if settings is not None else get_settings()
        super().__init__(
            base_url=config.api.gamma_api_url,
            settings=config,
            client_name="GammaAPI",
        )

    def get_markets(
        self,
        limit: int = 100,
        active: bool | None = None,
        closed: bool | None = None,
    ) -> list[Market]:
        """
        Fetch markets from the Gamma API.

        Args:
            limit: Maximum number of markets to return
            active: Filter by active status (None = no filter)
            closed: Filter by closed status (None = no filter)

        Returns:
            List of Market domain models

        Raises:
            HttpClientError: On request errors
            ApiClientError: On API errors
        """
        params: dict[str, int | bool] = {"limit": limit}

        if active is not None:
            params["active"] = active

        if closed is not None:
            params["closed"] = closed

        response = self.get("/markets", params=params)
        raw_markets = response.json()

        if not isinstance(raw_markets, list):
            raw_markets = []

        return [self._parse_market(m) for m in raw_markets]

    def get_market(self, condition_id: str) -> Market | None:
        """
        Fetch a specific market by condition ID.

        Args:
            condition_id: Market condition ID

        Returns:
            Market domain model, or None if not found
        """
        # Note: Gamma API doesn't have a direct /markets/{id} endpoint
        # We need to filter by condition_id
        markets = self.get_markets(limit=1000)
        for market in markets:
            if market.condition_id == condition_id:
                return market
        return None

    def get_markets_by_ids(
        self,
        condition_ids: list[str],
    ) -> list[Market]:
        """
        Fetch multiple markets by their condition IDs.

        Args:
            condition_ids: List of condition IDs

        Returns:
            List of Market domain models (only those found)
        """
        id_set = set(condition_ids)
        all_markets = self.get_markets(limit=1000)

        return [m for m in all_markets if m.condition_id in id_set]

    def get_active_markets(self, limit: int = 100) -> list[Market]:
        """
        Fetch only active (still trading) markets.

        Args:
            limit: Maximum number of markets to return

        Returns:
            List of active Market domain models
        """
        return self.get_markets(limit=limit, active=True, closed=False)

    def get_resolved_markets(self, limit: int = 100) -> list[Market]:
        """
        Fetch only resolved (closed with outcome) markets.

        Args:
            limit: Maximum number of markets to return

        Returns:
            List of resolved Market domain models
        """
        # Gamma API uses "closed" for resolved markets
        markets = self.get_markets(limit=limit, closed=True)
        # Filter to only those with a resolution
        return [m for m in markets if m.resolution is not None]

    def _parse_market(self, raw: dict) -> Market:
        """
        Convert raw API response to Market domain model.

        Args:
            raw: Raw market data from API

        Returns:
            Market domain model
        """
        # Parse outcomes from JSON string
        outcomes = ["yes", "no"]  # Default
        raw_outcomes = raw.get("outcomes")
        if raw_outcomes:
            try:
                if isinstance(raw_outcomes, str):
                    outcomes = json.loads(raw_outcomes)
                elif isinstance(raw_outcomes, list):
                    outcomes = raw_outcomes
            except (json.JSONDecodeError, TypeError):
                pass

        # Parse end date
        end_time = None
        raw_end = raw.get("endDate")
        if raw_end:
            try:
                # Handle various date formats
                if isinstance(raw_end, str):
                    # ISO format: "2020-11-04T00:00:00Z"
                    if "T" in raw_end:
                        end_time = datetime.fromisoformat(raw_end.replace("Z", "+00:00"))
                    else:
                        # Simple date: "2020-11-04"
                        end_time = datetime.strptime(raw_end, "%Y-%m-%d").replace(
                            tzinfo=timezone.utc
                        )
            except (ValueError, AttributeError):
                pass

        # Get resolution
        resolution = None
        resolved_outcome_id = raw.get("resolvedOutcomeId")
        if resolved_outcome_id:
            # Map outcome ID to outcome name
            # This is a simplified mapping - may need enhancement
            outcome_ids = raw.get("clobTokenIds")
            if outcome_ids:
                try:
                    if isinstance(outcome_ids, str):
                        ids = json.loads(outcome_ids)
                    else:
                        ids = outcome_ids

                    for i, outcome_id in enumerate(ids):
                        if outcome_id == resolved_outcome_id and i < len(outcomes):
                            resolution = outcomes[i]
                            break
                except (json.JSONDecodeError, TypeError, IndexError):
                    pass

        # Parse volume and liquidity
        volume = None
        raw_volume = raw.get("volumeNum")
        if raw_volume is not None:
            try:
                volume = float(raw_volume)
            except (ValueError, TypeError):
                pass

        liquidity = None
        raw_liquidity = raw.get("liquidityNum")
        if raw_liquidity is not None:
            try:
                liquidity = float(raw_liquidity)
            except (ValueError, TypeError):
                pass

        # Parse creation time
        created_time = None
        raw_created = raw.get("createdAt")
        if raw_created:
            try:
                created_time = datetime.fromisoformat(
                    raw_created.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        return Market(
            condition_id=raw.get("conditionId", raw.get("id", "")),
            question=raw.get("question", ""),
            outcomes=outcomes,
            end_time=end_time,
            resolution=resolution,
            description=raw.get("description"),
            volume=volume,
            liquidity=liquidity,
            created_time=created_time,
        )

    def search_markets(
        self,
        query: str,
        limit: int = 20,
    ) -> list[Market]:
        """
        Search for markets by question text.

        Note: This is a client-side search as the API doesn't provide
        a search endpoint. For large datasets, this would be inefficient.

        Args:
            query: Search query string
            limit: Maximum results to return

        Returns:
            List of matching Market domain models
        """
        markets = self.get_markets(limit=1000)
        query_lower = query.lower()

        matches = [
            m
            for m in markets
            if query_lower in m.question.lower()
            or (m.description and query_lower in m.description.lower())
        ]

        return matches[:limit]
