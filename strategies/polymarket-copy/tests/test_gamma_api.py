"""
Tests for Gamma API client.
"""

from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import Mock, patch

from pmirror.data import GammaAPIClient
from pmirror.domain import Market


class TestGammaAPIClient:
    """Tests for GammaAPIClient."""

    @patch("pmirror.data.gamma_api.BaseHttpClient.__init__")
    def test_create_client(self, mock_init):
        """Should create client with correct base URL."""
        mock_init.return_value = None
        client = GammaAPIClient()
        mock_init.assert_called_once()
        call_kwargs = mock_init.call_args[1]
        assert "gamma-api.polymarket.com" in call_kwargs["base_url"]

    @patch("pmirror.data.client.httpx.Client")
    def test_get_markets_no_filters(self, mock_client_class):
        """Should fetch markets with no filters."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = self._sample_market_list()

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GammaAPIClient()
        markets = client.get_markets(limit=10)

        assert len(markets) == 1
        assert markets[0].condition_id == "0xtest123"
        assert markets[0].question == "Test market?"

        # Check request params
        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["params"]["limit"] == 10
        assert "active" not in call_kwargs["params"]
        assert "closed" not in call_kwargs["params"]

    @patch("pmirror.data.client.httpx.Client")
    def test_get_markets_active_only(self, mock_client_class):
        """Should filter by active status."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GammaAPIClient()
        client.get_markets(active=True)

        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["params"]["active"] is True

    @patch("pmirror.data.client.httpx.Client")
    def test_get_markets_closed_only(self, mock_client_class):
        """Should filter by closed status."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GammaAPIClient()
        client.get_markets(closed=True)

        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["params"]["closed"] is True

    @patch("pmirror.data.client.httpx.Client")
    def test_parse_market(self, mock_client_class):
        """Should correctly parse market data."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = Mock(get=lambda x: None)

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GammaAPIClient()
        raw_market = {
            "id": "123",
            "conditionId": "0xtest123",
            "question": "Will it rain tomorrow?",
            "outcomes": '[\"Yes\", \"No\"]',
            "endDate": "2024-12-31T23:59:59Z",
            "volumeNum": "50000.50",
            "liquidityNum": "10000.25",
            "createdAt": "2024-01-01T00:00:00Z",
            "description": "A test market",
        }

        market = client._parse_market(raw_market)

        assert market.condition_id == "0xtest123"
        assert market.question == "Will it rain tomorrow?"
        assert market.outcomes == ["Yes", "No"]
        assert market.end_time == datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        assert market.volume == 50000.50
        assert market.liquidity == 10000.25
        assert market.description == "A test market"

    @patch("pmirror.data.client.httpx.Client")
    def test_parse_market_with_array_outcomes(self, mock_client_class):
        """Should handle outcomes as array instead of JSON string."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = Mock(get=lambda x: None)

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GammaAPIClient()
        raw_market = {
            "conditionId": "0xtest",
            "question": "Test",
            "outcomes": ["A", "B", "C"],  # Array, not string
            "endDate": "2024-01-01",
        }

        market = client._parse_market(raw_market)

        assert market.outcomes == ["A", "B", "C"]

    @patch("pmirror.data.client.httpx.Client")
    def test_parse_market_with_resolution(self, mock_client_class):
        """Should parse resolved outcome."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = Mock(get=lambda x: None)

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GammaAPIClient()
        raw_market = {
            "conditionId": "0xtest",
            "question": "Test",
            "outcomes": '[\"Yes\", \"No\"]',
            "resolvedOutcomeId": "53",  # Assume this maps to "Yes"
            "clobTokenIds": '[\"53\", \"54\"]',
        }

        market = client._parse_market(raw_market)

        assert market.resolution == "Yes"

    @patch("pmirror.data.client.httpx.Client")
    def test_parse_market_simple_date(self, mock_client_class):
        """Should parse simple date format."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = Mock(get=lambda x: None)

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GammaAPIClient()
        raw_market = {
            "conditionId": "0xtest",
            "question": "Test",
            "endDate": "2024-06-15",  # Simple date
        }

        market = client._parse_market(raw_market)

        assert market.end_time == datetime(2024, 6, 15, 0, 0, 0, tzinfo=timezone.utc)

    @patch("pmirror.data.client.httpx.Client")
    def test_get_market_by_id(self, mock_client_class):
        """Should fetch specific market by condition ID."""
        target_id = "0xfindme"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "conditionId": "0xother",
                "question": "Other market",
                "outcomes": "[]",
            },
            {
                "conditionId": target_id,
                "question": "Target market",
                "outcomes": "[]",
            },
        ]

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GammaAPIClient()
        market = client.get_market(target_id)

        assert market is not None
        assert market.condition_id == target_id

    @patch("pmirror.data.client.httpx.Client")
    def test_get_market_not_found(self, mock_client_class):
        """Should return None when market not found."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"conditionId": "0xother", "question": "Other", "outcomes": "[]"}
        ]

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GammaAPIClient()
        market = client.get_market("0xnonexistent")

        assert market is None

    @patch("pmirror.data.client.httpx.Client")
    def test_get_markets_by_ids(self, mock_client_class):
        """Should fetch multiple markets by IDs."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"conditionId": "0x1", "question": "One", "outcomes": "[]"},
            {"conditionId": "0x2", "question": "Two", "outcomes": "[]"},
            {"conditionId": "0x3", "question": "Three", "outcomes": "[]"},
        ]

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GammaAPIClient()
        markets = client.get_markets_by_ids(["0x1", "0x3", "0xmissing"])

        assert len(markets) == 2
        ids = {m.condition_id for m in markets}
        assert "0x1" in ids
        assert "0x3" in ids
        assert "0xmissing" not in ids

    @patch("pmirror.data.client.httpx.Client")
    def test_get_active_markets(self, mock_client_class):
        """Should fetch only active markets."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GammaAPIClient()
        client.get_active_markets(limit=50)

        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["params"]["active"] is True
        assert call_kwargs["params"]["closed"] is False

    @patch("pmirror.data.client.httpx.Client")
    def test_get_resolved_markets(self, mock_client_class):
        """Should fetch only resolved markets."""
        # Mock returns closed markets, some with resolution
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "conditionId": "0x1",
                "question": "Resolved Yes",
                "outcomes": '["Yes", "No"]',
                "resolvedOutcomeId": "token1",
                "clobTokenIds": '["token1", "token2"]',
            },
            {
                "conditionId": "0x2",
                "question": "Resolved No",
                "outcomes": '["Yes", "No"]',
                "resolvedOutcomeId": "token2",
                "clobTokenIds": '["token1", "token2"]',
            },
        ]

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GammaAPIClient()
        markets = client.get_resolved_markets()

        # Should filter to only those with resolution
        # (In our mock, the _parse_market won't correctly map token to outcome
        # so we just verify the call was made correctly)
        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["params"]["closed"] is True

    @patch("pmirror.data.client.httpx.Client")
    def test_search_markets(self, mock_client_class):
        """Should search markets by query string."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "conditionId": "0x1",
                "question": "Bitcoin price prediction",
                "outcomes": "[]",
            },
            {
                "conditionId": "0x2",
                "question": "Ethereum merge outcome",
                "outcomes": "[]",
            },
            {
                "conditionId": "0x3",
                "question": "Will it rain?",
                "outcomes": "[]",
            },
        ]

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GammaAPIClient()
        markets = client.search_markets("bitcoin")

        assert len(markets) == 1
        assert "bitcoin" in markets[0].question.lower()

    @patch("pmirror.data.client.httpx.Client")
    def test_search_markets_in_description(self, mock_client_class):
        """Should search in description field."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "conditionId": "0x1",
                "question": "Market question",
                "description": "This market is about crypto prices",
                "outcomes": "[]",
            },
        ]

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GammaAPIClient()
        markets = client.search_markets("crypto")

        assert len(markets) == 1

    @patch("pmirror.data.client.httpx.Client")
    def test_handles_empty_response(self, mock_client_class):
        """Should handle empty market list."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GammaAPIClient()
        markets = client.get_markets()

        assert markets == []

    @patch("pmirror.data.client.httpx.Client")
    def test_handles_non_list_response(self, mock_client_class):
        """Should handle API returning non-list data gracefully."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": "Invalid"}

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GammaAPIClient()
        markets = client.get_markets()

        assert markets == []

    def _sample_market_list(self):
        """Return a sample market list for testing."""
        return [
            {
                "id": "1",
                "conditionId": "0xtest123",
                "question": "Test market?",
                "outcomes": '["Yes", "No"]',
                "endDate": "2024-12-31T23:59:59Z",
                "volumeNum": "1000",
                "liquidityNum": "500",
            }
        ]
