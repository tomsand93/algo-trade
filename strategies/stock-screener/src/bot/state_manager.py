"""SQLite state persistence for trading bot."""

import sqlite3
import logging
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class StateManager:
    """
    Manages bot state in SQLite.

    Tables:
    - positions: Current open positions
    - trades: Closed trade history
    - daily_snapshots: Daily portfolio snapshots
    """

    def __init__(self, db_path: str):
        """
        Initialize database connection and create tables.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        self._create_tables()

    def _create_tables(self):
        """Create database tables if they don't exist."""
        cursor = self.conn.cursor()

        # Positions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL UNIQUE,
                qty REAL NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL,
                take_profit REAL,
                rank_score REAL,
                entry_date TEXT NOT NULL,
                main_order_id TEXT,
                sl_order_id TEXT,
                tp_order_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Trades table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                exit_date TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL NOT NULL,
                qty REAL NOT NULL,
                pnl REAL NOT NULL,
                exit_reason TEXT NOT NULL,
                rank_score_entry REAL,
                rank_score_exit REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Daily snapshots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                portfolio_value REAL NOT NULL,
                cash REAL NOT NULL,
                buying_power REAL NOT NULL,
                positions_count INTEGER NOT NULL,
                open_positions TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.conn.commit()
        logger.info(f"Database tables created/verified at {self.db_path}")

    def save_position(
        self,
        symbol: str,
        qty: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        rank_score: float,
        main_order_id: Optional[str] = None,
        sl_order_id: Optional[str] = None,
        tp_order_id: Optional[str] = None
    ) -> int:
        """
        Save or update a position.

        Args:
            symbol: Stock symbol
            qty: Quantity of shares
            entry_price: Average entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            rank_score: Rank score at entry
            main_order_id: Main order ID from Alpaca
            sl_order_id: Stop loss order ID
            tp_order_id: Take profit order ID

        Returns:
            Row ID of the saved position
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO positions
            (symbol, qty, entry_price, stop_loss, take_profit, rank_score,
             entry_date, main_order_id, sl_order_id, tp_order_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol, qty, entry_price, stop_loss, take_profit, rank_score,
            datetime.now().isoformat(), main_order_id, sl_order_id, tp_order_id
        ))

        self.conn.commit()
        return cursor.lastrowid

    def get_all_positions(self) -> List[Dict]:
        """
        Get all open positions.

        Returns:
            List of position dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM positions")
        return [dict(row) for row in cursor.fetchall()]

    def get_position(self, symbol: str) -> Optional[Dict]:
        """
        Get position for specific symbol.

        Args:
            symbol: Stock symbol to look up

        Returns:
            Position dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM positions WHERE symbol = ?", (symbol,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def remove_position(self, symbol: str) -> bool:
        """
        Remove a position.

        Args:
            symbol: Stock symbol to remove

        Returns:
            True if position was removed, False if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
        self.conn.commit()
        return cursor.rowcount > 0

    def log_trade(
        self,
        symbol: str,
        entry_date: str,
        exit_date: str,
        entry_price: float,
        exit_price: float,
        qty: float,
        pnl: float,
        exit_reason: str,
        rank_score_entry: Optional[float] = None,
        rank_score_exit: Optional[float] = None
    ) -> int:
        """
        Log a closed trade.

        Args:
            symbol: Stock symbol
            entry_date: Entry date (ISO format string)
            exit_date: Exit date (ISO format string)
            entry_price: Entry price
            exit_price: Exit price
            qty: Quantity of shares
            pnl: Profit/loss amount
            exit_reason: Reason for exit (sl, tp, score_drop, etc.)
            rank_score_entry: Rank score at entry
            rank_score_exit: Rank score at exit

        Returns:
            Row ID of the logged trade
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO trades
            (symbol, entry_date, exit_date, entry_price, exit_price,
             qty, pnl, exit_reason, rank_score_entry, rank_score_exit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol, entry_date, exit_date, entry_price, exit_price,
            qty, pnl, exit_reason, rank_score_entry, rank_score_exit
        ))

        self.conn.commit()
        return cursor.lastrowid

    def get_all_trades(self, limit: Optional[int] = None) -> List[Dict]:
        """
        Get all trades, optionally limited.

        Args:
            limit: Maximum number of trades to return (most recent first)

        Returns:
            List of trade dictionaries
        """
        cursor = self.conn.cursor()
        if limit:
            cursor.execute(
                "SELECT * FROM trades ORDER BY entry_date DESC LIMIT ?",
                (limit,)
            )
        else:
            cursor.execute("SELECT * FROM trades ORDER BY entry_date DESC")
        return [dict(row) for row in cursor.fetchall()]

    def save_snapshot(
        self,
        date: str,
        portfolio_value: float,
        cash: float,
        buying_power: float,
        positions_count: int,
        open_positions: Optional[str] = None
    ) -> int:
        """
        Save daily portfolio snapshot.

        Args:
            date: Date string (YYYY-MM-DD format)
            portfolio_value: Total portfolio value
            cash: Available cash
            buying_power: Buying power
            positions_count: Number of open positions
            open_positions: Comma-separated list of position symbols

        Returns:
            Row ID of the saved snapshot
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO daily_snapshots
            (date, portfolio_value, cash, buying_power, positions_count, open_positions)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (date, portfolio_value, cash, buying_power, positions_count, open_positions))

        self.conn.commit()
        return cursor.lastrowid

    def get_latest_snapshot(self) -> Optional[Dict]:
        """
        Get most recent snapshot.

        Returns:
            Snapshot dictionary or None if no snapshots exist
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM daily_snapshots ORDER BY date DESC LIMIT 1")
        row = cursor.fetchone()
        return dict(row) if row else None

    def close(self):
        """Close database connection."""
        self.conn.close()
