"""
SQLite Database Manager for OHLCV Data

Features:
- Fast storage and retrieval of OHLCV data
- Incremental updates (only fetch new candles)
- Automatic staleness detection
- Metadata tracking for each symbol/timeframe
"""
import sqlite3
import pandas as pd
from datetime import datetime
from pathlib import Path
import config


class OHLCVDatabase:
    """Manages OHLCV data in SQLite database"""

    def __init__(self, db_path=None):
        """
        Initialize database connection

        Args:
            db_path: Path to database file (default: config.DATABASE_PATH)
        """
        self.db_path = db_path or config.DATABASE_PATH
        self.conn = None
        self._connect()
        self._create_tables()

    def _connect(self):
        """Establish database connection"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        # Enable foreign keys and performance optimizations
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")

    def _create_tables(self):
        """Create database tables and indexes"""
        cursor = self.conn.cursor()

        # OHLCV data table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ohlcv (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                PRIMARY KEY (symbol, timeframe, timestamp)
            )
        """)

        # Create index for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbol_timeframe_ts
            ON ohlcv(symbol, timeframe, timestamp)
        """)

        # Metadata table for tracking updates
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                first_timestamp INTEGER NOT NULL,
                last_timestamp INTEGER NOT NULL,
                last_update INTEGER NOT NULL,
                num_candles INTEGER NOT NULL,
                PRIMARY KEY (symbol, timeframe)
            )
        """)

        self.conn.commit()

    def save_ohlcv(self, df, symbol, timeframe):
        """
        Save OHLCV data to database

        Args:
            df: DataFrame with OHLCV data (index=timestamp)
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframe: Candle timeframe (e.g., '1h')
        """
        if df.empty:
            return

        # Prepare data
        df_copy = df.copy().reset_index()
        df_copy['symbol'] = symbol
        df_copy['timeframe'] = timeframe

        # Convert timestamp to Unix milliseconds
        df_copy['timestamp'] = pd.to_datetime(df_copy['timestamp']).astype('int64') // 10**6

        # Reorder columns
        df_copy = df_copy[['symbol', 'timeframe', 'timestamp', 'open', 'high', 'low', 'close', 'volume']]

        # Insert data (replace on conflict)
        df_copy.to_sql('ohlcv', self.conn, if_exists='append', index=False, method='multi')

        # Update metadata
        self._update_metadata(symbol, timeframe)

        print(f"✓ Saved {len(df_copy)} candles: {symbol} {timeframe}")

    def _update_metadata(self, symbol, timeframe):
        """Update metadata after saving data"""
        cursor = self.conn.cursor()

        # Get statistics
        cursor.execute("""
            SELECT
                MIN(timestamp) as first_ts,
                MAX(timestamp) as last_ts,
                COUNT(*) as count
            FROM ohlcv
            WHERE symbol = ? AND timeframe = ?
        """, (symbol, timeframe))

        row = cursor.fetchone()
        if row and row[0]:
            first_ts, last_ts, count = row
            current_time = int(datetime.now().timestamp() * 1000)

            cursor.execute("""
                INSERT OR REPLACE INTO metadata
                (symbol, timeframe, first_timestamp, last_timestamp, last_update, num_candles)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (symbol, timeframe, first_ts, last_ts, current_time, count))

            self.conn.commit()

    def load_ohlcv(self, symbol, timeframe, start_time=None, end_time=None):
        """
        Load OHLCV data from database

        Args:
            symbol: Trading pair
            timeframe: Candle timeframe
            start_time: Optional start timestamp (datetime or Unix ms)
            end_time: Optional end timestamp (datetime or Unix ms)

        Returns:
            DataFrame with OHLCV data
        """
        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv
            WHERE symbol = ? AND timeframe = ?
        """
        params = [symbol, timeframe]

        if start_time is not None:
            if isinstance(start_time, datetime):
                start_time = int(start_time.timestamp() * 1000)
            query += " AND timestamp >= ?"
            params.append(start_time)

        if end_time is not None:
            if isinstance(end_time, datetime):
                end_time = int(end_time.timestamp() * 1000)
            query += " AND timestamp <= ?"
            params.append(end_time)

        query += " ORDER BY timestamp ASC"

        df = pd.read_sql_query(query, self.conn, params=params)

        if df.empty:
            return pd.DataFrame()

        # Convert timestamp to datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)

        return df

    def get_metadata(self, symbol, timeframe):
        """
        Get metadata for symbol/timeframe

        Returns:
            dict or None
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT first_timestamp, last_timestamp, last_update, num_candles
            FROM metadata
            WHERE symbol = ? AND timeframe = ?
        """, (symbol, timeframe))

        row = cursor.fetchone()
        if row is None:
            return None

        return {
            'first_timestamp': row[0],
            'last_timestamp': row[1],
            'last_update': row[2],
            'num_candles': row[3]
        }

    def needs_update(self, symbol, timeframe, max_age_hours=1):
        """
        Check if data needs updating

        Args:
            symbol: Trading pair
            timeframe: Candle timeframe
            max_age_hours: Maximum age in hours

        Returns:
            bool: True if update needed
        """
        metadata = self.get_metadata(symbol, timeframe)

        if metadata is None:
            return True  # No data exists

        last_update = metadata['last_update']
        current_time = int(datetime.now().timestamp() * 1000)
        age_hours = (current_time - last_update) / (1000 * 60 * 60)

        return age_hours > max_age_hours

    def get_last_timestamp(self, symbol, timeframe):
        """
        Get last timestamp in database

        Returns:
            int: Unix timestamp in milliseconds or None
        """
        metadata = self.get_metadata(symbol, timeframe)
        return metadata['last_timestamp'] if metadata else None

    def delete_data(self, symbol, timeframe):
        """Delete all data for symbol/timeframe"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM ohlcv WHERE symbol = ? AND timeframe = ?", (symbol, timeframe))
        cursor.execute("DELETE FROM metadata WHERE symbol = ? AND timeframe = ?", (symbol, timeframe))
        self.conn.commit()
        print(f"✓ Deleted: {symbol} {timeframe}")

    def get_all_pairs(self):
        """Get all symbol/timeframe pairs in database"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT symbol, timeframe FROM metadata ORDER BY symbol, timeframe")
        return cursor.fetchall()

    def get_stats(self):
        """Get database statistics"""
        cursor = self.conn.cursor()

        # Total candles
        cursor.execute("SELECT COUNT(*) FROM ohlcv")
        total_candles = cursor.fetchone()[0]

        # Total pairs
        cursor.execute("SELECT COUNT(*) FROM metadata")
        total_pairs = cursor.fetchone()[0]

        # Top pairs by candle count
        cursor.execute("""
            SELECT symbol, timeframe, num_candles
            FROM metadata
            ORDER BY num_candles DESC
            LIMIT 10
        """)
        top_pairs = cursor.fetchall()

        return {
            'total_candles': total_candles,
            'total_pairs': total_pairs,
            'top_pairs': top_pairs,
            'db_size_mb': self._get_db_size()
        }

    def _get_db_size(self):
        """Get database file size in MB"""
        if not self.db_path.exists():
            return 0
        return self.db_path.stat().st_size / (1024 * 1024)

    def optimize(self):
        """Optimize database (vacuum and analyze)"""
        print("Optimizing database...")
        self.conn.execute("VACUUM")
        self.conn.execute("ANALYZE")
        self.conn.commit()
        print("✓ Database optimized")

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


if __name__ == "__main__":
    # Test database
    with OHLCVDatabase() as db:
        stats = db.get_stats()
        print("\nDatabase Statistics:")
        print(f"  Total Candles: {stats['total_candles']:,}")
        print(f"  Total Pairs: {stats['total_pairs']}")
        print(f"  Database Size: {stats['db_size_mb']:.2f} MB")
