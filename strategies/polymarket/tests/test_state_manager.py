"""TDD tests for StateManager — save_state() and load_state()."""
import json
import os
import pytest
from datetime import datetime, timezone

from polymarket_bot.risk import RiskManager
from polymarket_bot.models import OpenPosition, SimulatedOrder


def make_rm(**kwargs) -> RiskManager:
    defaults = dict(
        initial_capital=100.0,
        max_position_size=10.0,
        daily_loss_limit=50.0,
        stop_loss_pct=0.20,
        cooldown_seconds=300,
    )
    defaults.update(kwargs)
    return RiskManager(**defaults)


def make_position(market_id="m1", side="YES", entry_price=0.65) -> OpenPosition:
    return OpenPosition(
        market_id=market_id,
        side=side,
        direction="BUY",
        entry_price=entry_price,
        quantity=round(10.0 / entry_price, 4),
        stop_loss_price=round(entry_price * 0.8, 4),
        opened_at=datetime.now(timezone.utc),
    )


class TestSaveState:
    def test_save_creates_file(self, tmp_path):
        from polymarket_bot.state_manager import save_state
        rm = make_rm()
        path = str(tmp_path / "positions.json")
        save_state(rm, path)
        assert os.path.exists(path)

    def test_save_creates_parent_directories(self, tmp_path):
        from polymarket_bot.state_manager import save_state
        rm = make_rm()
        path = str(tmp_path / "nested" / "deep" / "positions.json")
        save_state(rm, path)
        assert os.path.exists(path)

    def test_saved_file_is_valid_json(self, tmp_path):
        from polymarket_bot.state_manager import save_state
        rm = make_rm()
        path = str(tmp_path / "positions.json")
        save_state(rm, path)
        with open(path) as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_save_includes_daily_pnl(self, tmp_path):
        from polymarket_bot.state_manager import save_state
        rm = make_rm()
        rm._daily_pnl = -12.5
        path = str(tmp_path / "positions.json")
        save_state(rm, path)
        with open(path) as f:
            data = json.load(f)
        assert data["daily_pnl"] == pytest.approx(-12.5)

    def test_save_includes_positions(self, tmp_path):
        from polymarket_bot.state_manager import save_state
        rm = make_rm()
        rm._positions["m1"] = make_position("m1")
        path = str(tmp_path / "positions.json")
        save_state(rm, path)
        with open(path) as f:
            data = json.load(f)
        assert "m1" in data["positions"]

    def test_save_includes_halted_state(self, tmp_path):
        from polymarket_bot.state_manager import save_state
        rm = make_rm()
        rm._halted = True
        rm._halt_reason = "Circuit breaker: drawdown=-5%"
        path = str(tmp_path / "positions.json")
        save_state(rm, path)
        with open(path) as f:
            data = json.load(f)
        assert data["halted"] is True
        assert data["halt_reason"] == "Circuit breaker: drawdown=-5%"

    def test_save_includes_last_trade_times(self, tmp_path):
        from polymarket_bot.state_manager import save_state
        rm = make_rm()
        rm._last_trade_time["m1"] = datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc)
        path = str(tmp_path / "positions.json")
        save_state(rm, path)
        with open(path) as f:
            data = json.load(f)
        assert "m1" in data["last_trade_times"]


class TestLoadState:
    def test_returns_false_for_missing_file(self, tmp_path):
        from polymarket_bot.state_manager import load_state
        rm = make_rm()
        result = load_state(rm, str(tmp_path / "nonexistent.json"))
        assert result is False

    def test_returns_true_on_successful_load(self, tmp_path):
        from polymarket_bot.state_manager import save_state, load_state
        rm = make_rm()
        path = str(tmp_path / "positions.json")
        save_state(rm, path)
        rm2 = make_rm()
        result = load_state(rm2, path)
        assert result is True

    def test_returns_false_on_corrupt_json(self, tmp_path):
        from polymarket_bot.state_manager import load_state
        path = str(tmp_path / "positions.json")
        with open(path, "w") as f:
            f.write("{not valid json")
        rm = make_rm()
        result = load_state(rm, path)
        assert result is False

    def test_round_trip_daily_pnl(self, tmp_path):
        from polymarket_bot.state_manager import save_state, load_state
        rm = make_rm()
        rm._daily_pnl = -7.25
        path = str(tmp_path / "positions.json")
        save_state(rm, path)
        rm2 = make_rm()
        load_state(rm2, path)
        assert rm2._daily_pnl == pytest.approx(-7.25)

    def test_round_trip_portfolio_value(self, tmp_path):
        from polymarket_bot.state_manager import save_state, load_state
        rm = make_rm()
        rm._portfolio_value = 93.50
        rm._peak_value = 101.0
        path = str(tmp_path / "positions.json")
        save_state(rm, path)
        rm2 = make_rm()
        load_state(rm2, path)
        assert rm2._portfolio_value == pytest.approx(93.50)
        assert rm2._peak_value == pytest.approx(101.0)

    def test_round_trip_positions(self, tmp_path):
        from polymarket_bot.state_manager import save_state, load_state
        rm = make_rm()
        pos = make_position("m1", entry_price=0.65)
        rm._positions["m1"] = pos
        path = str(tmp_path / "positions.json")
        save_state(rm, path)
        rm2 = make_rm()
        load_state(rm2, path)
        assert "m1" in rm2._positions
        loaded = rm2._positions["m1"]
        assert loaded.entry_price == pytest.approx(0.65)
        assert loaded.side == "YES"

    def test_round_trip_multiple_positions(self, tmp_path):
        from polymarket_bot.state_manager import save_state, load_state
        rm = make_rm()
        rm._positions["m1"] = make_position("m1", entry_price=0.65)
        rm._positions["m2"] = make_position("m2", side="NO", entry_price=0.30)
        path = str(tmp_path / "positions.json")
        save_state(rm, path)
        rm2 = make_rm()
        load_state(rm2, path)
        assert len(rm2._positions) == 2
        assert rm2._positions["m2"].side == "NO"

    def test_round_trip_halted_state(self, tmp_path):
        from polymarket_bot.state_manager import save_state, load_state
        rm = make_rm()
        rm._halted = True
        rm._halt_reason = "Daily loss limit breached"
        path = str(tmp_path / "positions.json")
        save_state(rm, path)
        rm2 = make_rm()
        load_state(rm2, path)
        assert rm2._halted is True
        assert rm2._halt_reason == "Daily loss limit breached"

    def test_round_trip_last_trade_times(self, tmp_path):
        from polymarket_bot.state_manager import save_state, load_state
        rm = make_rm()
        ts = datetime(2026, 2, 28, 15, 30, 0, tzinfo=timezone.utc)
        rm._last_trade_time["m1"] = ts
        path = str(tmp_path / "positions.json")
        save_state(rm, path)
        rm2 = make_rm()
        load_state(rm2, path)
        assert "m1" in rm2._last_trade_time
        loaded_ts = rm2._last_trade_time["m1"]
        assert loaded_ts.year == 2026
        assert loaded_ts.month == 2
        assert loaded_ts.day == 28

    def test_load_does_not_crash_with_empty_positions(self, tmp_path):
        from polymarket_bot.state_manager import save_state, load_state
        rm = make_rm()  # no positions
        path = str(tmp_path / "positions.json")
        save_state(rm, path)
        rm2 = make_rm()
        result = load_state(rm2, path)
        assert result is True
        assert len(rm2._positions) == 0
