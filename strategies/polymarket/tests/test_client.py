"""Tests for ReplayClient and MockClient."""
import json
import pytest
from datetime import datetime, timezone
from polymarket_bot.models import MarketState


def make_valid_record(
    market_id: str = "0xtest",
    question: str = "Test market?",
    yes_price: float = 0.65,
    no_price: float = 0.35,
    volume_24h: float = 1000.0,
    captured_at: str = "2026-02-20T10:00:00",
) -> dict:
    return {
        "captured_at": captured_at,
        "market_id": market_id,
        "question": question,
        "yes_price": yes_price,
        "no_price": no_price,
        "volume_24h": volume_24h,
        "yes_token_id": "TOKEN_YES",
        "no_token_id": "TOKEN_NO",
    }


class TestReplayClient:
    """ReplayClient reads JSONL and yields valid MarketState objects."""

    def test_reads_single_valid_record(self, tmp_path):
        from polymarket_bot.client import ReplayClient
        jsonl = tmp_path / "snapshot.jsonl"
        record = make_valid_record()
        jsonl.write_text(json.dumps(record) + "\n", encoding="utf-8")

        client = ReplayClient(str(jsonl))
        states = list(client.get_market_states())

        assert len(states) == 1
        assert isinstance(states[0], MarketState)
        assert states[0].market_id == "0xtest"
        assert states[0].yes_price == 0.65

    def test_reads_multiple_records_in_order(self, tmp_path):
        from polymarket_bot.client import ReplayClient
        jsonl = tmp_path / "snapshot.jsonl"
        records = [
            make_valid_record(market_id="0x001", yes_price=0.65, no_price=0.35),
            make_valid_record(market_id="0x002", yes_price=0.30, no_price=0.70),
            make_valid_record(market_id="0x003", yes_price=0.80, no_price=0.20),
        ]
        jsonl.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

        client = ReplayClient(str(jsonl))
        states = list(client.get_market_states())

        assert len(states) == 3
        assert states[0].market_id == "0x001"
        assert states[1].market_id == "0x002"
        assert states[2].market_id == "0x003"

    def test_skips_malformed_json_line(self, tmp_path):
        """A truncated/malformed line is skipped, not a crash."""
        from polymarket_bot.client import ReplayClient
        jsonl = tmp_path / "snapshot.jsonl"
        good = make_valid_record(market_id="0xgood")
        # Write: good line, bad line, good line
        jsonl.write_text(
            json.dumps(good) + "\n"
            + "{this is not valid json\n"
            + json.dumps(make_valid_record(market_id="0xgood2")) + "\n",
            encoding="utf-8",
        )

        client = ReplayClient(str(jsonl))
        states = list(client.get_market_states())

        # Bad line is skipped; two good lines are returned
        assert len(states) == 2
        assert states[0].market_id == "0xgood"
        assert states[1].market_id == "0xgood2"

    def test_skips_blank_lines(self, tmp_path):
        from polymarket_bot.client import ReplayClient
        jsonl = tmp_path / "snapshot.jsonl"
        record = make_valid_record()
        jsonl.write_text("\n" + json.dumps(record) + "\n\n", encoding="utf-8")

        client = ReplayClient(str(jsonl))
        states = list(client.get_market_states())
        assert len(states) == 1

    def test_skips_record_with_invalid_prices(self, tmp_path):
        """Record with YES+NO not summing to ~1.00 is skipped."""
        from polymarket_bot.client import ReplayClient
        jsonl = tmp_path / "snapshot.jsonl"
        bad_record = make_valid_record(yes_price=0.5, no_price=0.6)  # sum = 1.1
        good_record = make_valid_record(market_id="0xgood", yes_price=0.65, no_price=0.35)
        jsonl.write_text(
            json.dumps(bad_record) + "\n" + json.dumps(good_record) + "\n",
            encoding="utf-8",
        )

        client = ReplayClient(str(jsonl))
        states = list(client.get_market_states())
        assert len(states) == 1
        assert states[0].market_id == "0xgood"

    def test_empty_file_returns_no_states(self, tmp_path):
        from polymarket_bot.client import ReplayClient
        jsonl = tmp_path / "empty.jsonl"
        jsonl.write_text("", encoding="utf-8")

        client = ReplayClient(str(jsonl))
        states = list(client.get_market_states())
        assert states == []


class TestMockClient:
    """MockClient generates synthetic but valid MarketState objects."""

    def test_generates_125_observations(self):
        """5 markets * 25 steps = 125 total observations (fills window=20 default)."""
        from polymarket_bot.client import MockClient
        client = MockClient(seed=42)
        states = list(client.get_market_states())
        assert len(states) == 125

    def test_all_states_are_valid_market_state(self):
        from polymarket_bot.client import MockClient
        client = MockClient(seed=99)
        for state in client.get_market_states():
            assert isinstance(state, MarketState)

    def test_prices_sum_to_one(self):
        from polymarket_bot.client import MockClient
        client = MockClient(seed=7)
        for state in client.get_market_states():
            total = state.yes_price + state.no_price
            assert abs(total - 1.0) <= 0.01, f"prices don't sum to 1: {total}"

    def test_prices_in_valid_range(self):
        from polymarket_bot.client import MockClient
        client = MockClient(seed=13)
        for state in client.get_market_states():
            assert 0.0 <= state.yes_price <= 1.0
            assert 0.0 <= state.no_price <= 1.0

    def test_seeded_output_is_reproducible(self):
        from polymarket_bot.client import MockClient
        states_a = list(MockClient(seed=42).get_market_states())
        states_b = list(MockClient(seed=42).get_market_states())
        assert [s.yes_price for s in states_a] == [s.yes_price for s in states_b]

    def test_different_seeds_produce_different_prices(self):
        from polymarket_bot.client import MockClient
        states_a = list(MockClient(seed=1).get_market_states())
        states_b = list(MockClient(seed=2).get_market_states())
        # At least one observation should differ
        prices_a = [s.yes_price for s in states_a]
        prices_b = [s.yes_price for s in states_b]
        assert prices_a != prices_b

    def test_cancel_order_returns_cancelled_status(self):
        """cancel_order(order_id) returns the SimulatedOrder with status='CANCELLED'."""
        from polymarket_bot.client import MockClient
        from polymarket_bot.models import SimulatedOrder
        from datetime import datetime, timezone
        client = MockClient(seed=0)
        order = SimulatedOrder(
            market_id="0xmock001",
            side="YES",
            direction="BUY",
            fill_price=0.65,
            quantity=1.0,
            timestamp=datetime.now(timezone.utc),
        )
        client.register_order(order)
        cancelled = client.cancel_order(order.order_id)
        assert cancelled.status == "CANCELLED"
        assert cancelled.order_id == order.order_id
        assert cancelled.market_id == order.market_id

    def test_cancel_order_removes_from_open_orders(self):
        """After cancellation, the order_id can no longer be cancelled again."""
        from polymarket_bot.client import MockClient
        from polymarket_bot.models import SimulatedOrder
        from datetime import datetime, timezone
        import pytest
        client = MockClient(seed=0)
        order = SimulatedOrder(
            market_id="0xmock001",
            side="YES",
            direction="BUY",
            fill_price=0.65,
            quantity=1.0,
            timestamp=datetime.now(timezone.utc),
        )
        client.register_order(order)
        client.cancel_order(order.order_id)
        # Second cancel raises KeyError — order already removed
        with pytest.raises(KeyError):
            client.cancel_order(order.order_id)


class TestPolymarketClient:
    """PolymarketClient with mocked ClobClient — no real network calls."""

    def _make_market(self, condition_id="0xcond1", active=True, closed=False,
                     yes_token_id="tok_yes_1", no_token_id="tok_no_1",
                     question="Will X happen?"):
        return {
            "condition_id": condition_id,
            "question": question,
            "active": active,
            "closed": closed,
            "volume": "50000.0",
            "tokens": [
                {"token_id": yes_token_id, "outcome": "Yes", "winner": False},
                {"token_id": no_token_id, "outcome": "No",  "winner": False},
            ],
        }

    def _make_clob_client_mock(self, markets, midpoint_value="0.65"):
        """Return a MagicMock that behaves like a ClobClient (single page)."""
        from unittest.mock import MagicMock
        mock = MagicMock()
        mock.get_simplified_markets.return_value = {
            "data": markets,
            "next_cursor": "LTE=",
        }
        mock.get_midpoint.return_value = {"mid": midpoint_value}
        return mock

    def test_yields_market_state_for_active_market(self, monkeypatch):
        from polymarket_bot.client import PolymarketClient
        from polymarket_bot.models import MarketState
        client = PolymarketClient()
        mock_clob = self._make_clob_client_mock([self._make_market()])
        client._clob = mock_clob
        states = list(client.get_market_states())
        assert len(states) == 1
        assert isinstance(states[0], MarketState)

    def test_uses_token_id_not_condition_id_for_midpoint(self, monkeypatch):
        """get_midpoint must be called with token_id from tokens array, not condition_id."""
        from polymarket_bot.client import PolymarketClient
        from unittest.mock import MagicMock
        client = PolymarketClient()
        mock_clob = self._make_clob_client_mock(
            [self._make_market(condition_id="0xcond1", yes_token_id="CORRECT_TOKEN_ID")]
        )
        client._clob = mock_clob
        list(client.get_market_states())
        # Must be called with YES token_id, not condition_id
        mock_clob.get_midpoint.assert_called_with("CORRECT_TOKEN_ID")

    def test_filters_inactive_markets(self):
        from polymarket_bot.client import PolymarketClient
        client = PolymarketClient()
        markets = [
            self._make_market(condition_id="0x1", active=True, closed=False),
            self._make_market(condition_id="0x2", active=False, closed=False),
            self._make_market(condition_id="0x3", active=True, closed=True),
        ]
        client._clob = self._make_clob_client_mock(markets)
        states = list(client.get_market_states())
        assert len(states) == 1
        assert states[0].market_id == "0x1"

    def test_clamps_yes_price_to_valid_range(self):
        from polymarket_bot.client import PolymarketClient
        client = PolymarketClient()
        mock_clob = self._make_clob_client_mock(
            [self._make_market()], midpoint_value="0.999"
        )
        client._clob = mock_clob
        states = list(client.get_market_states())
        assert states[0].yes_price <= 0.99

    def test_clamps_yes_price_above_zero(self):
        from polymarket_bot.client import PolymarketClient
        client = PolymarketClient()
        mock_clob = self._make_clob_client_mock(
            [self._make_market()], midpoint_value="0.0"
        )
        client._clob = mock_clob
        states = list(client.get_market_states())
        assert states[0].yes_price >= 0.01

    def test_no_price_is_complement_of_yes_price(self):
        from polymarket_bot.client import PolymarketClient
        client = PolymarketClient()
        client._clob = self._make_clob_client_mock([self._make_market()], midpoint_value="0.65")
        states = list(client.get_market_states())
        assert abs(states[0].yes_price + states[0].no_price - 1.0) < 0.01

    def test_skips_market_when_midpoint_raises(self):
        """Exception from get_midpoint is caught; market is skipped, loop continues."""
        from polymarket_bot.client import PolymarketClient
        from unittest.mock import MagicMock
        client = PolymarketClient()
        mock_clob = MagicMock()
        mock_clob.get_simplified_markets.return_value = {
            "data": [
                self._make_market(condition_id="0x1"),
                self._make_market(condition_id="0x2"),
            ],
            "next_cursor": "LTE=",
        }
        # First market raises; second returns valid data
        mock_clob.get_midpoint.side_effect = [
            Exception("API error"),
            {"mid": "0.55"},
        ]
        client._clob = mock_clob
        states = list(client.get_market_states())
        assert len(states) == 1
        assert states[0].market_id == "0x2"

    def test_skips_market_without_yes_token(self):
        from polymarket_bot.client import PolymarketClient
        from unittest.mock import MagicMock
        client = PolymarketClient()
        market_no_yes = {
            "condition_id": "0x1",
            "question": "Test?",
            "active": True,
            "closed": False,
            "volume": "1000",
            "tokens": [
                {"token_id": "no_tok", "outcome": "No", "winner": False},
            ],
        }
        mock_clob = MagicMock()
        mock_clob.get_simplified_markets.return_value = {"data": [market_no_yes], "next_cursor": "LTE="}
        client._clob = mock_clob
        states = list(client.get_market_states())
        assert len(states) == 0

    def test_volume_parsed_from_market_data(self):
        from polymarket_bot.client import PolymarketClient
        client = PolymarketClient()
        market = self._make_market()
        market["volume"] = "75000.5"
        client._clob = self._make_clob_client_mock([market])
        states = list(client.get_market_states())
        assert states[0].volume_24h == pytest.approx(75000.5)

    def test_returns_empty_on_no_active_markets(self):
        from polymarket_bot.client import PolymarketClient
        client = PolymarketClient()
        client._clob = self._make_clob_client_mock([])
        states = list(client.get_market_states())
        assert states == []

    def test_paginates_two_pages(self):
        """get_market_states() fetches all pages when next_cursor != 'LTE='."""
        from polymarket_bot.client import PolymarketClient
        from unittest.mock import MagicMock
        client = PolymarketClient()
        mock_clob = MagicMock()
        page1_market = self._make_market(condition_id="0x1", yes_token_id="tok1")
        page2_market = self._make_market(condition_id="0x2", yes_token_id="tok2")
        # First call returns page 1 with a real cursor; second call returns page 2 with terminal cursor
        mock_clob.get_simplified_markets.side_effect = [
            {"data": [page1_market], "next_cursor": "cursor_abc"},
            {"data": [page2_market], "next_cursor": "LTE="},
        ]
        mock_clob.get_midpoint.return_value = {"mid": "0.65"}
        client._clob = mock_clob
        states = list(client.get_market_states())
        assert len(states) == 2
        assert {s.market_id for s in states} == {"0x1", "0x2"}
        # Verify get_simplified_markets called twice with correct cursors
        calls = mock_clob.get_simplified_markets.call_args_list
        assert len(calls) == 2
        assert calls[0] == ((), {"next_cursor": None})
        assert calls[1] == ((), {"next_cursor": "cursor_abc"})


class TestPolymarketLiveClient:
    """PolymarketLiveClient with mocked ClobClient — no real API calls."""

    def _make_settings_mock(self, private_key="0xprivatekey", api_key="key123",
                            api_secret="secret123", passphrase="pass123",
                            signature_type=0):
        from unittest.mock import MagicMock
        from pydantic import SecretStr
        s = MagicMock()
        s.polymarket_private_key = SecretStr(private_key)
        s.polymarket_api_key = SecretStr(api_key)
        s.polymarket_api_secret = SecretStr(api_secret)
        s.polymarket_api_passphrase = SecretStr(passphrase)
        s.signature_type = signature_type
        return s

    def _make_signal_mock(self, market_id="m1", direction="BUY_YES", price=0.65):
        from unittest.mock import MagicMock
        sig = MagicMock()
        sig.market_id = market_id
        sig.direction = direction
        sig.price = price
        return sig

    def _make_market(self, condition_id="0xcond1", yes_token_id="tok_yes_1"):
        return {
            "condition_id": condition_id,
            "question": "Test?",
            "active": True,
            "closed": False,
            "volume": "10000.0",
            "tokens": [
                {"token_id": yes_token_id, "outcome": "Yes", "winner": False},
                {"token_id": "tok_no_1", "outcome": "No", "winner": False},
            ],
        }

    def test_get_market_states_delegates_to_clob(self):
        """PolymarketLiveClient.get_market_states() calls get_simplified_markets()."""
        from polymarket_bot.client import PolymarketLiveClient
        from unittest.mock import MagicMock, patch
        settings = self._make_settings_mock()
        with patch("py_clob_client.client.ClobClient") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.get_simplified_markets.return_value = {"data": [], "next_cursor": "LTE="}
            mock_cls.return_value = mock_instance
            client = PolymarketLiveClient(settings)
            states = list(client.get_market_states())
        assert states == []

    def test_get_market_states_populates_token_id_cache(self):
        """get_market_states() populates _token_id_cache with {condition_id -> yes_token_id}."""
        from polymarket_bot.client import PolymarketLiveClient
        from unittest.mock import MagicMock, patch
        settings = self._make_settings_mock()
        with patch("py_clob_client.client.ClobClient") as mock_cls:
            mock_clob = MagicMock()
            mock_cls.return_value = mock_clob
            mock_clob.get_simplified_markets.return_value = {
                "data": [self._make_market(condition_id="0xcond1", yes_token_id="YES_TOK_1")],
                "next_cursor": "LTE=",
            }
            mock_clob.get_midpoint.return_value = {"mid": "0.65"}
            client = PolymarketLiveClient(settings)
            list(client.get_market_states())
        assert client._token_id_cache.get("0xcond1") == "YES_TOK_1"

    def test_get_market_states_paginates_two_pages(self):
        """get_market_states() fetches all pages and caches tokens from all pages."""
        from polymarket_bot.client import PolymarketLiveClient
        from unittest.mock import MagicMock, patch
        settings = self._make_settings_mock()
        with patch("py_clob_client.client.ClobClient") as mock_cls:
            mock_clob = MagicMock()
            mock_cls.return_value = mock_clob
            mock_clob.get_simplified_markets.side_effect = [
                {"data": [self._make_market("0x1", "tok1")], "next_cursor": "cursor_xyz"},
                {"data": [self._make_market("0x2", "tok2")], "next_cursor": "LTE="},
            ]
            mock_clob.get_midpoint.return_value = {"mid": "0.55"}
            client = PolymarketLiveClient(settings)
            states = list(client.get_market_states())
        assert len(states) == 2
        assert client._token_id_cache["0x1"] == "tok1"
        assert client._token_id_cache["0x2"] == "tok2"

    def test_place_live_order_uses_cached_token_id(self):
        """place_live_order() resolves token_id from _token_id_cache[signal.market_id]."""
        from polymarket_bot.client import PolymarketLiveClient
        from unittest.mock import MagicMock, patch, call
        from py_clob_client.clob_types import OrderArgs
        settings = self._make_settings_mock()
        with patch("py_clob_client.client.ClobClient") as mock_cls:
            mock_clob = MagicMock()
            mock_cls.return_value = mock_clob
            mock_clob.create_order.return_value = MagicMock()
            mock_clob.post_order.return_value = {"status": "matched"}
            client = PolymarketLiveClient(settings)
            # Pre-populate cache as if get_market_states() had run
            client._token_id_cache["m1"] = "CACHED_YES_TOKEN"
            signal = self._make_signal_mock(market_id="m1", direction="BUY_YES", price=0.65)
            client.place_live_order(signal, max_position_size=10.0)
        # Verify create_order was called with the cached token_id
        create_call_args = mock_clob.create_order.call_args[0][0]
        assert create_call_args.token_id == "CACHED_YES_TOKEN"

    def test_place_live_order_calls_create_and_post_order(self):
        """place_live_order() calls create_order() then post_order()."""
        from polymarket_bot.client import PolymarketLiveClient
        from unittest.mock import MagicMock, patch
        settings = self._make_settings_mock()
        with patch("py_clob_client.client.ClobClient") as mock_cls:
            mock_clob = MagicMock()
            mock_cls.return_value = mock_clob
            mock_clob.create_order.return_value = MagicMock()
            mock_clob.post_order.return_value = {"status": "matched", "orderID": "ord123"}
            client = PolymarketLiveClient(settings)
            client._token_id_cache["m1"] = "tok_yes"
            signal = self._make_signal_mock(direction="BUY_YES", price=0.65)
            order = client.place_live_order(signal, max_position_size=10.0)
        mock_clob.create_order.assert_called_once()
        mock_clob.post_order.assert_called_once()

    def test_place_live_order_returns_simulated_order(self):
        """place_live_order() returns a SimulatedOrder for record_fill() compatibility."""
        from polymarket_bot.client import PolymarketLiveClient
        from polymarket_bot.models import SimulatedOrder
        from unittest.mock import MagicMock, patch
        settings = self._make_settings_mock()
        with patch("py_clob_client.client.ClobClient") as mock_cls:
            mock_clob = MagicMock()
            mock_cls.return_value = mock_clob
            mock_clob.create_order.return_value = MagicMock()
            mock_clob.post_order.return_value = {"status": "matched"}
            client = PolymarketLiveClient(settings)
            client._token_id_cache["m1"] = "tok_yes"
            signal = self._make_signal_mock(direction="BUY_YES", price=0.65)
            order = client.place_live_order(signal, max_position_size=10.0)
        assert isinstance(order, SimulatedOrder)
        assert order.market_id == "m1"
        assert order.direction == "BUY"
        assert order.side == "YES"

    def test_place_live_order_buy_no_direction(self):
        """BUY_NO signal results in side=NO, direction=BUY."""
        from polymarket_bot.client import PolymarketLiveClient
        from unittest.mock import MagicMock, patch
        settings = self._make_settings_mock()
        with patch("py_clob_client.client.ClobClient") as mock_cls:
            mock_clob = MagicMock()
            mock_cls.return_value = mock_clob
            mock_clob.create_order.return_value = MagicMock()
            mock_clob.post_order.return_value = {"status": "matched"}
            client = PolymarketLiveClient(settings)
            client._token_id_cache["m1"] = "tok_no"
            signal = self._make_signal_mock(direction="BUY_NO", price=0.35)
            order = client.place_live_order(signal, max_position_size=10.0)
        assert order.side == "NO"
        assert order.direction == "BUY"

    def test_place_live_order_quantity_is_capital_based(self):
        """quantity = max_position_size / price (same formula as simulate_order)."""
        from polymarket_bot.client import PolymarketLiveClient
        from unittest.mock import MagicMock, patch
        settings = self._make_settings_mock()
        with patch("py_clob_client.client.ClobClient") as mock_cls:
            mock_clob = MagicMock()
            mock_cls.return_value = mock_clob
            mock_clob.create_order.return_value = MagicMock()
            mock_clob.post_order.return_value = {}
            client = PolymarketLiveClient(settings)
            client._token_id_cache["m1"] = "tok"
            signal = self._make_signal_mock(price=0.50)
            order = client.place_live_order(signal, max_position_size=10.0)
        assert order.quantity == pytest.approx(20.0, abs=0.01)
