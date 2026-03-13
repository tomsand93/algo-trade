"""
Tests for Data API client.
"""

from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import Mock, patch

from pmirror.data import DataAPIClient
from pmirror.domain import Trade


class TestDataAPIClient:
    """Tests for DataAPIClient."""

    @patch("pmirror.data.data_api.BaseHttpClient.__init__")
    def test_create_client(self, mock_init):
        """Should create client with correct base URL."""
        mock_init.return_value = None
        client = DataAPIClient()
        mock_init.assert_called_once()
        # Check the base_url passed to parent (as keyword argument)
        call_kwargs = mock_init.call_args[1]
        assert "data-api.polymarket.com" in call_kwargs["base_url"]

    @patch("pmirror.data.client.httpx.Client")
    def test_get_trades_no_filters(self, mock_client_class):
        """Should fetch trades with no filters."""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "proxyWallet": "0xabc",
                "side": "BUY",
                "conditionId": "0xmkt",
                "size": 100.0,
                "price": 0.65,
                "timestamp": 1709251200,  # 2024-03-01 12:00:00 UTC
                "outcome": "yes",
                "transactionHash": "0xtx",
            }
        ]

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = DataAPIClient()
        trades = client.get_trades(limit=10)

        assert len(trades) == 1
        assert trades[0].maker == "0xabc"
        assert trades[0].side == "buy"
        assert trades[0].price == 0.65
        assert trades[0].size == 100.0

        # Check the request was made correctly
        mock_client.request.assert_called_once()
        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["params"]["limit"] == 10
        assert "maker" not in call_kwargs["params"]

    @patch("pmirror.data.client.httpx.Client")
    def test_get_trades_with_wallet(self, mock_client_class):
        """Should filter trades by wallet address."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = DataAPIClient()
        client.get_trades(maker="0xwallet123")

        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["params"]["maker"] == "0xwallet123"

    @patch("pmirror.data.client.httpx.Client")
    def test_get_trades_with_date_range(self, mock_client_class):
        """Should filter trades by date range."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = DataAPIClient()
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        client.get_trades(start=start, end=end)

        call_kwargs = mock_client.request.call_args[1]
        assert "start" in call_kwargs["params"]
        assert "end" in call_kwargs["params"]
        # Check timestamps are converted to integers
        assert isinstance(call_kwargs["params"]["start"], int)

    @patch("pmirror.data.client.httpx.Client")
    def test_parse_trade(self, mock_client_class):
        """Should correctly parse raw trade data to domain model."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = Mock(get=lambda x: None)

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = DataAPIClient()

        raw_trade = {
            "proxyWallet": "0xABC123",
            "side": "BUY",
            "conditionId": "0xmarket",
            "size": 250.5,
            "price": 0.70,
            "timestamp": 1709251200,
            "outcome": "yes",
            "outcomeIndex": 0,
            "transactionHash": "0xhash123",
        }

        trade = client._parse_trade(raw_trade)

        assert trade.maker == "0xabc123"  # Lowercased
        assert trade.side == "buy"  # Lowercased
        assert trade.market_id == "0xmarket"
        assert trade.price == 0.70
        assert trade.size == 250.5
        assert trade.outcome == "yes"
        assert trade.transaction_hash == "0xhash123"
        assert trade.taker is None  # Not provided by API
        # Timestamp is timezone-aware (UTC)
        assert trade.timestamp == datetime(2024, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
        # Shares should be computed
        assert trade.shares is not None
        assert abs(trade.shares - (250.5 / 0.70)) < 0.01

    @patch("pmirror.data.client.httpx.Client")
    def test_parse_sell_trade(self, mock_client_class):
        """Should correctly parse SELL trades."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = Mock(get=lambda x: None)

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = DataAPIClient()

        raw_trade = {
            "proxyWallet": "0xabc",
            "side": "SELL",
            "conditionId": "0xmkt",
            "size": 100,
            "price": 0.5,
            "timestamp": 1709251200,
            "outcome": "no",
            "transactionHash": "0xtx",
        }

        trade = client._parse_trade(raw_trade)

        assert trade.side == "sell"

    @patch("pmirror.data.client.httpx.Client")
    def test_get_recent_trades(self, mock_client_class):
        """Should fetch recent trades with default limit."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = DataAPIClient()
        client.get_recent_trades()

        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["params"]["limit"] == 100

    @patch("pmirror.data.client.httpx.Client")
    def test_get_recent_trades_custom_limit(self, mock_client_class):
        """Should fetch recent trades with custom limit."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = DataAPIClient()
        client.get_recent_trades(limit=50)

        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["params"]["limit"] == 50

    @patch("pmirror.data.client.httpx.Client")
    def test_get_wallet_trades(self, mock_client_class):
        """Should fetch trades for a specific wallet."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = DataAPIClient()
        wallet = "0xwallet456"
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        client.get_wallet_trades(wallet, start, end)

        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["params"]["maker"] == wallet
        assert "start" in call_kwargs["params"]
        assert "end" in call_kwargs["params"]

    @patch("pmirror.data.client.httpx.Client")
    def test_get_wallet_trades_custom_limit(self, mock_client_class):
        """Should respect custom limit for wallet trades."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = DataAPIClient()
        client.get_wallet_trades(
            "0xwallet",
            datetime(2024, 1, 1),
            datetime(2024, 1, 31),
            limit=500,
        )

        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["params"]["limit"] == 500

    @patch("pmirror.data.client.httpx.Client")
    def test_handles_empty_response(self, mock_client_class):
        """Should handle empty trade list."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = DataAPIClient()
        trades = client.get_trades()

        assert trades == []

    @patch("pmirror.data.client.httpx.Client")
    def test_handles_non_list_response(self, mock_client_class):
        """Should handle API returning non-list data gracefully."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": "Invalid request"}

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = DataAPIClient()
        trades = client.get_trades()

        # Should return empty list instead of crashing
        assert trades == []

    @patch("pmirror.data.client.httpx.Client")
    def test_get_trade_count(self, mock_client_class):
        """Should return trade count for wallet."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"proxyWallet": "0xabc", "side": "BUY", "conditionId": "0xm",
             "size": 100, "price": 0.5, "timestamp": 1709251200,
             "outcome": "yes", "transactionHash": "0xtx"},
            {"proxyWallet": "0xabc", "side": "SELL", "conditionId": "0xm",
             "size": 50, "price": 0.6, "timestamp": 1709251300,
             "outcome": "yes", "transactionHash": "0xtx2"},
        ]

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = DataAPIClient()
        count = client.get_trade_count(
            "0xabc",
            datetime(2024, 1, 1),
            datetime(2024, 1, 31),
        )

        # Note: Returns actual fetched count, not total available
        assert count == 2
