"""Tests for AlpacaClient."""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from src.broker.alpaca_client import AlpacaClient


def test_client_initialization_paper_mode():
    """Test paper mode client initialization."""
    with patch.dict(os.environ, {
        'ALPACA_PAPER_KEY': 'test_paper_key',
        'ALPACA_PAPER_SECRET': 'test_paper_secret'
    }):
        client = AlpacaClient(mode="paper")
        assert client.mode == "paper"
        assert client.key_id == "test_paper_key"
        assert client.secret_key == "test_paper_secret"


def test_client_initialization_live_mode():
    """Test live mode client initialization."""
    with patch.dict(os.environ, {
        'ALPACA_LIVE_KEY': 'test_live_key',
        'ALPACA_LIVE_SECRET': 'test_live_secret'
    }):
        client = AlpacaClient(mode="live")
        assert client.mode == "live"
        assert client.key_id == "test_live_key"
        assert client.secret_key == "test_live_secret"


def test_client_initialization_with_params():
    """Test client initialization with explicit key/secret params."""
    client = AlpacaClient(mode="paper", key="my_key", secret="my_secret")
    assert client.mode == "paper"
    assert client.key_id == "my_key"
    assert client.secret_key == "my_secret"


def test_client_initialization_missing_credentials():
    """Test that missing credentials raise ValueError."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="Alpaca credentials not found"):
            AlpacaClient(mode="paper")


def test_mode_lowercase():
    """Test that mode is converted to lowercase."""
    with patch.dict(os.environ, {
        'ALPACA_PAPER_KEY': 'test_key',
        'ALPACA_PAPER_SECRET': 'test_secret'
    }):
        client = AlpacaClient(mode="PAPER")
        assert client.mode == "paper"

        client = AlpacaClient(mode="Paper")
        assert client.mode == "paper"


def test_get_account():
    """Test getting account information."""
    with patch.dict(os.environ, {
        'ALPACA_PAPER_KEY': 'test_key',
        'ALPACA_PAPER_SECRET': 'test_secret'
    }):
        # Mock the TradingClient
        with patch('src.broker.alpaca_client.TradingClient') as mock_trading_client:
            # Create mock account response
            mock_account = Mock()
            mock_account.cash = "10000.50"
            mock_account.buying_power = "20000.00"
            mock_account.portfolio_value = "15000.75"
            mock_account.positions_count = 3

            mock_client_instance = Mock()
            mock_client_instance.get_account.return_value = mock_account
            mock_trading_client.return_value = mock_client_instance

            client = AlpacaClient(mode="paper")
            account_info = client.get_account()

            assert account_info.cash == 10000.50
            assert account_info.buying_power == 20000.00
            assert account_info.portfolio_value == 15000.75
            assert account_info.positions_count == 3


def test_get_positions():
    """Test getting all open positions."""
    with patch.dict(os.environ, {
        'ALPACA_PAPER_KEY': 'test_key',
        'ALPACA_PAPER_SECRET': 'test_secret'
    }):
        with patch('src.broker.alpaca_client.TradingClient') as mock_trading_client:
            # Create mock position responses
            mock_pos1 = Mock()
            mock_pos1.symbol = "AAPL"
            mock_pos1.quantity = "10"
            mock_pos1.avg_entry_price = "150.00"
            mock_pos1.current_price = "155.00"
            mock_pos1.unrealized_pl = "50.00"
            mock_pos1.unrealized_plpc = "3.33"
            mock_pos1.side = "long"

            mock_pos2 = Mock()
            mock_pos2.symbol = "MSFT"
            mock_pos2.quantity = "5"
            mock_pos2.avg_entry_price = "300.00"
            mock_pos2.current_price = "310.00"
            mock_pos2.unrealized_pl = "50.00"
            mock_pos2.unrealized_plpc = "3.33"
            mock_pos2.side = "long"

            mock_client_instance = Mock()
            mock_client_instance.get_all_positions.return_value = [mock_pos1, mock_pos2]
            mock_trading_client.return_value = mock_client_instance

            client = AlpacaClient(mode="paper")
            positions = client.get_positions()

            assert len(positions) == 2
            assert positions[0].symbol == "AAPL"
            assert positions[0].qty == 10
            assert positions[0].entry_price == 150.00
            assert positions[1].symbol == "MSFT"
            assert positions[1].qty == 5


def test_get_position():
    """Test getting position for specific symbol."""
    with patch.dict(os.environ, {
        'ALPACA_PAPER_KEY': 'test_key',
        'ALPACA_PAPER_SECRET': 'test_secret'
    }):
        with patch('src.broker.alpaca_client.TradingClient') as mock_trading_client:
            mock_pos = Mock()
            mock_pos.symbol = "AAPL"
            mock_pos.quantity = "10"
            mock_pos.avg_entry_price = "150.00"
            mock_pos.current_price = "155.00"
            mock_pos.unrealized_pl = "50.00"
            mock_pos.unrealized_plpc = "3.33"
            mock_pos.side = "long"

            mock_client_instance = Mock()
            mock_client_instance.get_open_position.return_value = mock_pos
            mock_trading_client.return_value = mock_client_instance

            client = AlpacaClient(mode="paper")
            position = client.get_position("AAPL")

            assert position is not None
            assert position.symbol == "AAPL"
            assert position.qty == 10


def test_get_position_not_found():
    """Test getting position that doesn't exist returns None."""
    with patch.dict(os.environ, {
        'ALPACA_PAPER_KEY': 'test_key',
        'ALPACA_PAPER_SECRET': 'test_secret'
    }):
        with patch('src.broker.alpaca_client.TradingClient') as mock_trading_client:
            mock_client_instance = Mock()
            mock_client_instance.get_open_position.side_effect = Exception("position not found")
            mock_trading_client.return_value = mock_client_instance

            client = AlpacaClient(mode="paper")
            position = client.get_position("NOTFOUND")

            assert position is None


def test_submit_market_order_buy():
    """Test submitting a buy market order."""
    with patch.dict(os.environ, {
        'ALPACA_PAPER_KEY': 'test_key',
        'ALPACA_PAPER_SECRET': 'test_secret'
    }):
        with patch('src.broker.alpaca_client.TradingClient') as mock_trading_client:
            mock_order = Mock()
            mock_order.id = "order_123"

            mock_client_instance = Mock()
            mock_client_instance.submit_order.return_value = mock_order
            mock_trading_client.return_value = mock_client_instance

            client = AlpacaClient(mode="paper")
            order_id = client.submit_market_order("AAPL", 10, "buy")

            assert order_id == "order_123"
            mock_client_instance.submit_order.assert_called_once()


def test_submit_market_order_sell():
    """Test submitting a sell market order."""
    with patch.dict(os.environ, {
        'ALPACA_PAPER_KEY': 'test_key',
        'ALPACA_PAPER_SECRET': 'test_secret'
    }):
        with patch('src.broker.alpaca_client.TradingClient') as mock_trading_client:
            mock_order = Mock()
            mock_order.id = "order_456"

            mock_client_instance = Mock()
            mock_client_instance.submit_order.return_value = mock_order
            mock_trading_client.return_value = mock_client_instance

            client = AlpacaClient(mode="paper")
            order_id = client.submit_market_order("AAPL", 10, "sell")

            assert order_id == "order_456"


def test_cancel_order():
    """Test canceling an order."""
    with patch.dict(os.environ, {
        'ALPACA_PAPER_KEY': 'test_key',
        'ALPACA_PAPER_SECRET': 'test_secret'
    }):
        with patch('src.broker.alpaca_client.TradingClient') as mock_trading_client:
            mock_client_instance = Mock()
            mock_trading_client.return_value = mock_client_instance

            client = AlpacaClient(mode="paper")
            result = client.cancel_order("order_123")

            assert result is True
            mock_client_instance.cancel_order_by_id.assert_called_once_with("order_123")


def test_cancel_order_failure():
    """Test canceling an order that fails."""
    with patch.dict(os.environ, {
        'ALPACA_PAPER_KEY': 'test_key',
        'ALPACA_PAPER_SECRET': 'test_secret'
    }):
        with patch('src.broker.alpaca_client.TradingClient') as mock_trading_client:
            mock_client_instance = Mock()
            mock_client_instance.cancel_order_by_id.side_effect = Exception("not found")
            mock_trading_client.return_value = mock_client_instance

            client = AlpacaClient(mode="paper")
            result = client.cancel_order("order_123")

            assert result is False


def test_submit_order_with_bracket():
    """Test submitting a bracket order with SL/TP."""
    with patch.dict(os.environ, {
        'ALPACA_PAPER_KEY': 'test_key',
        'ALPACA_PAPER_SECRET': 'test_secret'
    }):
        with patch('src.broker.alpaca_client.TradingClient') as mock_trading_client:
            mock_order = Mock()
            mock_order.id = "bracket_order_123"

            mock_client_instance = Mock()
            mock_client_instance.submit_order.return_value = mock_order
            mock_trading_client.return_value = mock_client_instance

            client = AlpacaClient(mode="paper")
            result = client.submit_order_with_bracket(
                symbol="AAPL",
                qty=10,
                side="buy",
                take_profit=165.0,
                stop_loss=145.0
            )

            assert result["main_order_id"] == "bracket_order_123"
            mock_client_instance.submit_order.assert_called_once()


def test_is_market_open():
    """Test checking if market is open."""
    with patch.dict(os.environ, {
        'ALPACA_PAPER_KEY': 'test_key',
        'ALPACA_PAPER_SECRET': 'test_secret'
    }):
        with patch('src.broker.alpaca_client.TradingClient') as mock_trading_client:
            mock_clock = Mock()
            mock_clock.is_open = True

            mock_client_instance = Mock()
            mock_client_instance.get_clock.return_value = mock_clock
            mock_trading_client.return_value = mock_client_instance

            client = AlpacaClient(mode="paper")
            is_open = client.is_market_open()

            assert is_open is True


def test_get_next_market_open():
    """Test getting next market open time."""
    with patch.dict(os.environ, {
        'ALPACA_PAPER_KEY': 'test_key',
        'ALPACA_PAPER_SECRET': 'test_secret'
    }):
        with patch('src.broker.alpaca_client.TradingClient') as mock_trading_client:
            from datetime import datetime
            test_time = datetime(2025, 2, 24, 9, 30, 0)

            mock_clock = Mock()
            mock_clock.next_open = Mock()
            mock_clock.next_open.timestamp = test_time

            mock_client_instance = Mock()
            mock_client_instance.get_clock.return_value = mock_clock
            mock_trading_client.return_value = mock_client_instance

            client = AlpacaClient(mode="paper")
            next_open = client.get_next_market_open()

            assert next_open == test_time
