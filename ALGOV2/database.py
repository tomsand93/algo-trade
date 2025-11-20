"""
SQLite Database Manager for Historical OHLCV Data

Features:
- Stores OHLCV data in SQLite for fast access
- Tracks last update timestamp per symbol/timeframe
- Only downloads new candles (incremental updates)
- Much faster than CSV files
- Automatic data freshness checking
"""
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import config


class OHLCVDatabase:
    """Manage OHLCV data in SQLite database"""

    def __init__(self, db_path=None):
        """
        Initialize database connection

        Args:
            db_path: Path to SQLite database file (default: data/ohlcv.db)
        """
        if db_path is None:
            db_path = config.DATA_DIR / "ohlcv.db"

        self.db_path = db_path
        self.conn = None
        self._connect()
        self._create_tables()

    def _connect(self):
        """Connect to SQLite database"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))

    def _create_tables(self):
        """Create database tables if they don't exist"""
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
            CREATE INDEX IF NOT EXISTS idx_symbol_timeframe
            ON ohlcv(symbol, timeframe, timestamp)
        """)

        # Metadata table to track last update
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                last_update INTEGER NOT NULL,
                last_timestamp INTEGER NOT NULL,
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

        # Prepare data for insertion
        df_copy = df.copy()
        df_copy.reset_index(inplace=True)
        df_copy['symbol'] = symbol
        df_copy['timeframe'] = timeframe

        # Convert timestamp to Unix milliseconds
        df_copy['timestamp'] = pd.to_datetime(df_copy['timestamp']).astype('int64') // 10**6

        # Select columns in correct order
        df_copy = df_copy[['symbol', 'timeframe', 'timestamp', 'open', 'high', 'low', 'close', 'volume']]

        # Insert or replace data
        df_copy.to_sql('ohlcv', self.conn, if_exists='append', index=False, method='multi')

        # Update metadata
        last_timestamp = int(df_copy['timestamp'].max())
        num_candles = len(df_copy)
        current_time = int(datetime.now().timestamp() * 1000)

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO metadata (symbol, timeframe, last_update, last_timestamp, num_candles)
            VALUES (?, ?, ?, ?, ?)
        """, (symbol, timeframe, current_time, last_timestamp, num_candles))

        self.conn.commit()

        print(f"✓ Saved {num_candles} candles to database: {symbol} {timeframe}")

    def load_ohlcv(self, symbol, timeframe, start_time=None, end_time=None):
        """
        Load OHLCV data from database

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframe: Candle timeframe (e.g., '1h')
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

        # Convert timestamp back to datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)

        return df

    def get_metadata(self, symbol, timeframe):
        """
        Get metadata for symbol/timeframe

        Returns:
            dict with last_update, last_timestamp, num_candles or None
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT last_update, last_timestamp, num_candles
            FROM metadata
            WHERE symbol = ? AND timeframe = ?
        """, (symbol, timeframe))

        row = cursor.fetchone()

        if row is None:
            return None

        return {
            'last_update': row[0],
            'last_timestamp': row[1],
            'num_candles': row[2]
        }

    def needs_update(self, symbol, timeframe, max_age_hours=1):
        """
        Check if data needs updating

        Args:
            symbol: Trading pair
            timeframe: Candle timeframe
            max_age_hours: Maximum age in hours before update needed

        Returns:
            bool: True if data needs updating
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
        Get the last timestamp in database for symbol/timeframe

        Returns:
            int: Unix timestamp in milliseconds or None
        """
        metadata = self.get_metadata(symbol, timeframe)

        if metadata is None:
            return None

        return metadata['last_timestamp']

    def delete_data(self, symbol, timeframe):
        """Delete all data for symbol/timeframe"""
        cursor = self.conn.cursor()

        cursor.execute("DELETE FROM ohlcv WHERE symbol = ? AND timeframe = ?", (symbol, timeframe))
        cursor.execute("DELETE FROM metadata WHERE symbol = ? AND timeframe = ?", (symbol, timeframe))

        self.conn.commit()
        print(f"✓ Deleted data: {symbol} {timeframe}")

    def get_all_symbols(self):
        """Get list of all symbols/timeframes in database"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT symbol, timeframe FROM metadata")
        return cursor.fetchall()

    def get_stats(self):
        """Get database statistics"""
        cursor = self.conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM ohlcv")
        total_candles = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM metadata")
        total_pairs = cursor.fetchone()[0]

        cursor.execute("SELECT symbol, timeframe, num_candles FROM metadata ORDER BY num_candles DESC LIMIT 10")
        top_pairs = cursor.fetchall()

        return {
            'total_candles': total_candles,
            'total_pairs': total_pairs,
            'top_pairs': top_pairs
        }

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


def migrate_csv_to_database():
    """Migrate existing CSV files to database"""
    from data_fetcher import BinanceDataFetcher

    db = OHLCVDatabase()
    fetcher = BinanceDataFetcher(use_testnet=False)

    print("=" * 70)
    print("MIGRATING CSV FILES TO DATABASE")
    print("=" * 70)

    migrated = 0
    for asset in config.CRYPTO_ASSETS:
        if asset.endswith('USDT'):
            symbol = f"{asset[:-4]}/USDT"
        else:
            symbol = asset

        for timeframe in config.CRYPTO_INTERVALS:
            df = fetcher.load_from_csv(symbol, timeframe)

            if df is not None and not df.empty:
                db.save_ohlcv(df, symbol, timeframe)
                migrated += 1

    print(f"\n✓ Migrated {migrated} CSV files to database")
    print("=" * 70)

    db.close()


if __name__ == "__main__":
    # Test database
    db = OHLCVDatabase()
    stats = db.get_stats()
    print(f"Database Stats: {stats}")
    db.close()
