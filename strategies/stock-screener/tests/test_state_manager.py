"""Tests for StateManager."""

import shutil
import uuid
from pathlib import Path

import pytest

from src.bot.state_manager import StateManager


@pytest.fixture
def db_path():
    base = Path(".tmp_pytest") / f"state-{uuid.uuid4().hex}"
    base.mkdir(parents=True, exist_ok=True)
    path = base / "test.db"
    try:
        yield str(path)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_state_manager_initialization(db_path):
    manager = StateManager(db_path)
    assert manager.db_path == db_path
    manager.close()


def test_save_and_load_position(db_path):
    manager = StateManager(db_path)

    manager.save_position(
        symbol="AAPL",
        qty=10,
        entry_price=150.0,
        stop_loss=145.0,
        take_profit=165.0,
        rank_score=75.5,
    )

    positions = manager.get_all_positions()
    assert len(positions) == 1
    assert positions[0]["symbol"] == "AAPL"
    assert positions[0]["qty"] == 10
    assert positions[0]["entry_price"] == 150.0
    manager.close()


def test_save_position_with_order_ids(db_path):
    manager = StateManager(db_path)

    position_id = manager.save_position(
        symbol="MSFT",
        qty=5,
        entry_price=300.0,
        stop_loss=290.0,
        take_profit=330.0,
        rank_score=80.0,
        main_order_id="order_main_123",
        sl_order_id="order_sl_456",
        tp_order_id="order_tp_789",
    )

    assert position_id > 0

    position = manager.get_position("MSFT")
    assert position is not None
    assert position["main_order_id"] == "order_main_123"
    assert position["sl_order_id"] == "order_sl_456"
    assert position["tp_order_id"] == "order_tp_789"
    manager.close()


def test_update_existing_position(db_path):
    manager = StateManager(db_path)

    manager.save_position(
        symbol="AAPL",
        qty=10,
        entry_price=150.0,
        stop_loss=145.0,
        take_profit=165.0,
        rank_score=75.5,
    )

    manager.save_position(
        symbol="AAPL",
        qty=15,
        entry_price=155.0,
        stop_loss=140.0,
        take_profit=170.0,
        rank_score=78.0,
    )

    positions = manager.get_all_positions()
    assert len(positions) == 1
    assert positions[0]["qty"] == 15
    assert positions[0]["entry_price"] == 155.0
    manager.close()


def test_remove_position(db_path):
    manager = StateManager(db_path)
    manager.save_position("AAPL", 10, 150.0, 145.0, 165.0, 75.5)
    assert len(manager.get_all_positions()) == 1
    assert manager.remove_position("AAPL") is True
    assert len(manager.get_all_positions()) == 0
    manager.close()


def test_remove_nonexistent_position(db_path):
    manager = StateManager(db_path)
    assert manager.remove_position("NOTFOUND") is False
    manager.close()


def test_get_position_by_symbol(db_path):
    manager = StateManager(db_path)
    manager.save_position("AAPL", 10, 150.0, 145.0, 165.0, 75.5)

    position = manager.get_position("AAPL")
    assert position is not None
    assert position["symbol"] == "AAPL"
    assert position["qty"] == 10
    assert manager.get_position("MSFT") is None
    manager.close()


def test_log_trade(db_path):
    manager = StateManager(db_path)
    manager.log_trade("AAPL", "2025-02-23", "2025-02-24", 150.0, 155.0, 10, 50.0, "take_profit")

    trades = manager.get_all_trades()
    assert len(trades) == 1
    assert trades[0]["pnl"] == 50.0
    assert trades[0]["exit_reason"] == "take_profit"
    assert trades[0]["symbol"] == "AAPL"
    manager.close()


def test_log_trade_with_rank_scores(db_path):
    manager = StateManager(db_path)

    trade_id = manager.log_trade(
        symbol="MSFT",
        entry_date="2025-02-20",
        exit_date="2025-02-24",
        entry_price=300.0,
        exit_price=310.0,
        qty=5,
        pnl=50.0,
        exit_reason="score_drop",
        rank_score_entry=75.0,
        rank_score_exit=45.0,
    )

    assert trade_id > 0
    trades = manager.get_all_trades()
    assert len(trades) == 1
    assert trades[0]["rank_score_entry"] == 75.0
    assert trades[0]["rank_score_exit"] == 45.0
    manager.close()


def test_get_trades_with_limit(db_path):
    manager = StateManager(db_path)

    for i in range(5):
        manager.log_trade(
            symbol=f"STOCK{i}",
            entry_date=f"2025-02-{20+i}",
            exit_date=f"2025-02-{25+i}",
            entry_price=100.0 + i,
            exit_price=105.0 + i,
            qty=10,
            pnl=50.0,
            exit_reason="take_profit",
        )

    assert len(manager.get_all_trades()) == 5
    assert len(manager.get_all_trades(limit=3)) == 3
    manager.close()


def test_save_snapshot(db_path):
    manager = StateManager(db_path)
    manager.save_snapshot("2025-02-23", 15000.50, 5000.00, 10000.00, 3, "AAPL,MSFT,GOOGL")

    snapshot = manager.get_latest_snapshot()
    assert snapshot is not None
    assert snapshot["date"] == "2025-02-23"
    assert snapshot["portfolio_value"] == 15000.50
    assert snapshot["cash"] == 5000.00
    assert snapshot["positions_count"] == 3
    assert snapshot["open_positions"] == "AAPL,MSFT,GOOGL"
    manager.close()


def test_update_snapshot(db_path):
    manager = StateManager(db_path)
    manager.save_snapshot("2025-02-23", 15000.50, 5000.00, 10000.00, 3)
    manager.save_snapshot("2025-02-23", 15500.00, 4500.00, 9500.00, 4)

    snapshot = manager.get_latest_snapshot()
    assert snapshot["portfolio_value"] == 15500.00
    assert snapshot["positions_count"] == 4
    manager.close()


def test_get_latest_snapshot_when_empty(db_path):
    manager = StateManager(db_path)
    assert manager.get_latest_snapshot() is None
    manager.close()


def test_multiple_positions_and_trades(db_path):
    manager = StateManager(db_path)

    symbols = ["AAPL", "MSFT", "GOOGL"]
    for i, symbol in enumerate(symbols):
        manager.save_position(
            symbol=symbol,
            qty=10 + i * 5,
            entry_price=150.0 + i * 50,
            stop_loss=145.0 + i * 50,
            take_profit=165.0 + i * 50,
            rank_score=70.0 + i * 5,
        )

    assert len(manager.get_all_positions()) == 3

    for i in range(3):
        manager.log_trade(
            symbol=f"STOCK{i}",
            entry_date="2025-02-20",
            exit_date="2025-02-23",
            entry_price=100.0,
            exit_price=110.0,
            qty=10,
            pnl=100.0,
            exit_reason="take_profit",
        )

    assert len(manager.get_all_trades()) == 3
    manager.close()


def test_db_path_parent_directory_created():
    base = Path(".tmp_pytest") / f"nested-{uuid.uuid4().hex}"
    nested_path = base / "nested" / "dir" / "test.db"
    try:
        manager = StateManager(str(nested_path))
        assert nested_path.exists()
        assert manager.db_path == str(nested_path)
        manager.close()
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_close_connection(db_path):
    manager = StateManager(db_path)
    manager.save_position("AAPL", 10, 150.0, 145.0, 165.0, 75.5)
    manager.close()

    with pytest.raises(Exception):
        manager.get_all_positions()
