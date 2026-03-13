"""Integration tests for run_loop() — verifying RiskManager is wired correctly.

Tests use MockClient for deterministic market data and a real RiskManager.
Focus: verify the Phase 2 call chain (check_stops → signal → should_trade → risk.check → order → record_fill).
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from polymarket_bot.models import MarketState, Signal, SimulatedOrder
from polymarket_bot.risk import RiskManager
from polymarket_bot.strategy import MeanReversionStrategy, MomentumStrategy
from run import run_loop, simulate_order


# ─── Helpers ────────────────────────────────────────────────────────────────

def make_rm(**kwargs) -> RiskManager:
    defaults = dict(
        initial_capital=100.0,
        max_position_size=10.0,
        daily_loss_limit=50.0,
        stop_loss_pct=0.20,
        cooldown_seconds=0,  # cooldown=0 so we can test freely in mock
    )
    defaults.update(kwargs)
    return RiskManager(**defaults)


def make_market_state(market_id="m1", yes_price=0.50) -> MarketState:
    return MarketState(
        market_id=market_id,
        question="Will X happen?",
        yes_price=yes_price,
        no_price=round(1.0 - yes_price, 4),
        volume_24h=1000.0,
        timestamp=datetime.now(timezone.utc),
    )


class FakeClient:
    """Client that yields a fixed list of MarketState objects."""
    def __init__(self, states):
        self.states = states

    def get_market_states(self):
        return iter(self.states)


class AlwaysSignalStrategy(MeanReversionStrategy):
    """Strategy that returns a BUY_YES signal for every market state (ignores window)."""

    def generate_signal(self, market_state):
        return Signal(
            market_id=market_state.market_id,
            direction="BUY_YES",
            confidence=0.9,
            price=market_state.yes_price,
            reason="forced test signal",
        )

    def should_trade(self, signal, market_state):
        return True


class NeverSignalStrategy(MeanReversionStrategy):
    """Strategy that never generates a signal."""

    def generate_signal(self, market_state):
        return None

    def should_trade(self, signal, market_state):
        return True


# ─── Tests ──────────────────────────────────────────────────────────────────

class TestSimulateOrder:
    def test_quantity_is_capital_based(self):
        """simulate_order uses max_position_size / fill_price for quantity."""
        sig = Signal(market_id="m1", direction="BUY_YES", confidence=0.8, price=0.50, reason="t")
        ms = make_market_state(yes_price=0.50)
        order = simulate_order(sig, ms, max_position_size=10.0)
        assert order.quantity == pytest.approx(20.0, abs=0.001)

    def test_quantity_adjusts_with_price(self):
        """Lower price → more tokens for same capital."""
        sig = Signal(market_id="m1", direction="BUY_YES", confidence=0.8, price=0.25, reason="t")
        ms = make_market_state(yes_price=0.25)
        order = simulate_order(sig, ms, max_position_size=10.0)
        assert order.quantity == pytest.approx(40.0, abs=0.01)

    def test_simulate_order_side_yes(self):
        sig = Signal(market_id="m1", direction="BUY_YES", confidence=0.8, price=0.50, reason="t")
        order = simulate_order(sig, make_market_state(), max_position_size=10.0)
        assert order.side == "YES"
        assert order.direction == "BUY"

    def test_simulate_order_side_no(self):
        sig = Signal(market_id="m1", direction="BUY_NO", confidence=0.8, price=0.50, reason="t")
        order = simulate_order(sig, make_market_state(), max_position_size=10.0)
        assert order.side == "NO"
        assert order.direction == "BUY"


class TestRunLoop:
    def test_run_loop_returns_signal_count(self):
        """run_loop returns the number of signals generated (not orders placed)."""
        states = [make_market_state("m1"), make_market_state("m2")]
        client = FakeClient(states)
        strategy = AlwaysSignalStrategy()
        rm = make_rm()
        count = run_loop(client, strategy, rm)
        assert count == 2  # 2 signals generated (one per market state)

    def test_run_loop_zero_signals_for_no_signal_strategy(self):
        """run_loop returns 0 when strategy generates no signals."""
        states = [make_market_state("m1"), make_market_state("m2")]
        client = FakeClient(states)
        strategy = NeverSignalStrategy()
        rm = make_rm()
        count = run_loop(client, strategy, rm)
        assert count == 0

    def test_run_loop_calls_risk_manager_check(self):
        """risk_manager.check() is called for every signal generated."""
        states = [make_market_state("m1")]
        client = FakeClient(states)
        strategy = AlwaysSignalStrategy()
        rm = make_rm()

        original_check = rm.check
        check_calls = []

        def tracking_check(signal, market_state):
            check_calls.append((signal, market_state))
            return original_check(signal, market_state)

        rm.check = tracking_check
        run_loop(client, strategy, rm)
        assert len(check_calls) == 1

    def test_run_loop_calls_check_stops_for_every_state(self):
        """risk_manager.check_stops() is called for every market state, not just signals."""
        states = [make_market_state("m1"), make_market_state("m2")]
        client = FakeClient(states)
        strategy = NeverSignalStrategy()  # no signals generated
        rm = make_rm()

        stop_calls = []
        original_check_stops = rm.check_stops

        def tracking_check_stops(market_state):
            stop_calls.append(market_state)
            return original_check_stops(market_state)

        rm.check_stops = tracking_check_stops
        run_loop(client, strategy, rm)
        assert len(stop_calls) == 2  # called even when no signal

    def test_run_loop_blocks_orders_when_halted(self):
        """Halted RiskManager produces 0 orders even with signals present."""
        states = [make_market_state("m1"), make_market_state("m2")]
        client = FakeClient(states)
        strategy = AlwaysSignalStrategy()
        rm = make_rm()
        rm._halted = True  # pre-halt
        # Signal count still increments (signals generated), but no orders placed
        count = run_loop(client, strategy, rm)
        assert count == 2
        # Verify no positions recorded (no orders went through)
        assert len(rm._positions) == 0

    def test_run_loop_records_fill_after_order(self):
        """After an order is placed, RiskManager has the position recorded."""
        states = [make_market_state("m1", yes_price=0.50)]
        client = FakeClient(states)
        strategy = AlwaysSignalStrategy()
        rm = make_rm()
        run_loop(client, strategy, rm)
        assert "m1" in rm._positions
        pos = rm._positions["m1"]
        assert pos.entry_price == pytest.approx(0.50, abs=1e-4)

    def test_run_loop_with_mock_client_smoke(self):
        """End-to-end smoke test: MockClient + MeanReversionStrategy + RiskManager."""
        from polymarket_bot.client import MockClient
        client = MockClient()
        strategy = MeanReversionStrategy(window=7, z_entry=2.0, z_exit=0.5)
        rm = make_rm()
        count = run_loop(client, strategy, rm)
        # MockClient generates multiple states; signal count may be 0 (window not filled yet)
        assert isinstance(count, int)
        assert count >= 0

    def test_run_loop_with_momentum_strategy_smoke(self):
        """Smoke test: MockClient + MomentumStrategy + RiskManager runs without error."""
        from polymarket_bot.client import MockClient
        client = MockClient()
        strategy = MomentumStrategy(short_window=3, long_window=7)
        rm = make_rm()
        count = run_loop(client, strategy, rm)
        assert isinstance(count, int)
        assert count >= 0


class TestRunLoopLiveMode:
    """run_loop() with live_mode=True calls place_live_order() instead of simulate_order()."""

    def test_run_loop_live_mode_calls_place_live_order(self):
        """live_mode=True: client.place_live_order() called instead of simulate_order()."""
        from unittest.mock import MagicMock, patch, call
        from polymarket_bot.models import SimulatedOrder
        from datetime import datetime, timezone

        states = [make_market_state("m1", yes_price=0.50)]
        mock_order = SimulatedOrder(
            market_id="m1", side="YES", direction="BUY",
            fill_price=0.50, quantity=20.0, status="FILLED",
            timestamp=datetime.now(timezone.utc),
        )

        client = MagicMock()
        client.get_market_states.return_value = iter(states)
        client.place_live_order.return_value = mock_order

        strategy = AlwaysSignalStrategy()
        rm = make_rm()

        count = run_loop(client, strategy, rm, live_mode=True)

        # place_live_order called with (signal, max_position_size) — NO token_id argument
        # PolymarketLiveClient resolves token_id internally from _token_id_cache
        client.place_live_order.assert_called_once()
        call_args = client.place_live_order.call_args
        assert len(call_args[0]) == 2 or "max_position_size" in str(call_args)
        assert count == 1
        # Position recorded from live order
        assert "m1" in rm._positions

    def test_run_loop_paper_mode_does_not_call_place_live_order(self):
        """live_mode=False (default): place_live_order() is never called."""
        from unittest.mock import MagicMock
        states = [make_market_state("m1", yes_price=0.50)]
        client = MagicMock()
        client.get_market_states.return_value = iter(states)

        strategy = AlwaysSignalStrategy()
        rm = make_rm()

        run_loop(client, strategy, rm, live_mode=False)

        client.place_live_order.assert_not_called()

    def test_run_loop_backward_compatible_no_live_mode_param(self):
        """Existing 3-argument call still works (live_mode defaults to False)."""
        states = [make_market_state("m1")]
        client = FakeClient(states)
        strategy = AlwaysSignalStrategy()
        rm = make_rm()
        # Must not raise TypeError
        count = run_loop(client, strategy, rm)
        assert isinstance(count, int)


class TestHandleSignalAndShutdown:
    """_handle_signal sets _shutdown flag; run_paper_or_live exits loop on shutdown."""

    def test_shutdown_flag_set_by_handle_signal(self):
        """_handle_signal(signum, frame) sets run._shutdown to True."""
        import run as run_module
        run_module._shutdown = False
        run_module._handle_signal(2, None)  # 2 = SIGINT
        assert run_module._shutdown is True
        run_module._shutdown = False  # reset for other tests

    def test_run_paper_or_live_stops_when_shutdown_flag_set(self):
        """run_paper_or_live() exits loop after first tick when _shutdown is True."""
        import run as run_module
        from unittest.mock import MagicMock, patch

        client = MagicMock()
        client.get_market_states.return_value = iter([])

        strategy = MagicMock()
        rm = make_rm()
        settings = MagicMock()
        settings.poll_interval_seconds = 0
        settings.state_file = "data/state/positions.json"

        call_count = [0]

        def fake_run_loop(*args, **kwargs):
            call_count[0] += 1
            run_module._shutdown = True  # set shutdown after first tick
            return 0

        with patch("run.run_loop", fake_run_loop):
            with patch("polymarket_bot.state_manager.save_state"):
                run_module._shutdown = False
                run_module.run_paper_or_live(client, strategy, rm, settings, live=False)

        assert call_count[0] == 1  # only one tick executed

    def test_save_state_called_on_shutdown(self):
        """save_state() is called after the loop exits (not in signal handler).

        NOTE: polymarket_bot.state_manager.save_state is patched at module path rather than
        run.save_state because run.py imports save_state via a LOCAL import inside
        run_paper_or_live() (`from polymarket_bot.state_manager import save_state`).
        This local-import pattern is intentional: save_state must NOT be imported at module
        level in run.py because signal handlers call nothing from that module, and keeping
        the import local makes the dependency explicit and avoids circular import risk.
        If the import is ever moved to module level, update the patch target to `run.save_state`.
        """
        import run as run_module
        from unittest.mock import MagicMock, patch

        client = MagicMock()
        client.get_market_states.return_value = iter([])
        strategy = MagicMock()
        rm = make_rm()
        settings = MagicMock()
        settings.poll_interval_seconds = 0
        settings.state_file = "data/state/test_positions.json"

        saved = []

        def fake_run_loop(*args, **kwargs):
            run_module._shutdown = True
            return 0

        def fake_save(risk_manager, path):
            saved.append(path)

        with patch("run.run_loop", fake_run_loop):
            with patch("polymarket_bot.state_manager.save_state", fake_save):
                run_module._shutdown = False
                run_module.run_paper_or_live(client, strategy, rm, settings, live=False)

        assert len(saved) == 1
        assert saved[0] == "data/state/test_positions.json"

    def test_run_paper_or_live_continues_after_exception(self):
        """Exception in run_loop tick is caught and loop continues to next tick."""
        import run as run_module
        from unittest.mock import MagicMock, patch

        client = MagicMock()
        strategy = MagicMock()
        rm = make_rm()
        settings = MagicMock()
        settings.poll_interval_seconds = 0
        settings.state_file = "data/state/test_positions.json"

        tick_count = [0]

        def fake_run_loop(*args, **kwargs):
            tick_count[0] += 1
            if tick_count[0] == 1:
                raise RuntimeError("Simulated tick failure")
            run_module._shutdown = True
            return 0

        with patch("run.run_loop", fake_run_loop):
            with patch("polymarket_bot.state_manager.save_state"):
                run_module._shutdown = False
                run_module.run_paper_or_live(client, strategy, rm, settings, live=False)

        # Loop ran twice: tick 1 raised exception (recovered), tick 2 set shutdown and exited
        assert tick_count[0] == 2


class TestRunLivePreflight:
    """_run_live_preflight() exits on API failure, wrong auth level, or no wallet address."""

    def test_preflight_passes_with_valid_l2_client(self):
        """Preflight passes when API reachable, L2 auth, and address resolves."""
        from unittest.mock import MagicMock
        from run import _run_live_preflight
        client = MagicMock()
        client._clob.get_ok.return_value = True
        client._clob.mode = 2
        client._clob.get_address.return_value = "0xWalletAddress"
        settings = MagicMock()
        settings.max_position_size = 10.0
        settings.daily_loss_limit = 50.0
        # Must not raise or sys.exit
        _run_live_preflight(client, settings)

    def test_preflight_exits_when_api_unreachable(self):
        """sys.exit(1) when get_ok() raises Exception."""
        from unittest.mock import MagicMock
        from run import _run_live_preflight
        import pytest
        client = MagicMock()
        client._clob.get_ok.side_effect = Exception("Connection refused")
        settings = MagicMock()
        with pytest.raises(SystemExit) as exc_info:
            _run_live_preflight(client, settings)
        assert exc_info.value.code == 1

    def test_preflight_exits_when_not_l2_mode(self):
        """sys.exit(1) when client is not L2 (mode < 2)."""
        from unittest.mock import MagicMock
        from run import _run_live_preflight
        import pytest
        client = MagicMock()
        client._clob.get_ok.return_value = True
        client._clob.mode = 0  # L0 only
        settings = MagicMock()
        with pytest.raises(SystemExit) as exc_info:
            _run_live_preflight(client, settings)
        assert exc_info.value.code == 1

    def test_preflight_exits_when_address_not_resolved(self):
        """sys.exit(1) when get_address() returns empty string or None."""
        from unittest.mock import MagicMock
        from run import _run_live_preflight
        import pytest
        client = MagicMock()
        client._clob.get_ok.return_value = True
        client._clob.mode = 2
        client._clob.get_address.return_value = ""
        settings = MagicMock()
        with pytest.raises(SystemExit) as exc_info:
            _run_live_preflight(client, settings)
        assert exc_info.value.code == 1
