"""
Enhanced Data Fetcher with SQLite Database Support

Features:
- Stores data in SQLite database (much faster than CSV)
- Incremental updates (only downloads NEW candles)
- Automatic staleness detection
- Fallback to CSV for compatibility
- Smart caching with freshness checking
"""
import ccxt
import pandas as pd
from datetime import datetime, timedelta
import time
from pathlib import Path
import config
from database import OHLCVDatabase


class BinanceDataFetcherV2:
    """Enhanced Binance data fetcher with database support"""

    def __init__(self, use_testnet=False, use_database=True):
        """
        Initialize Binance connection

        Args:
            use_testnet: If True, use testnet credentials
            use_database: If True, use SQLite database (recommended)
        """
        if use_testnet:
            self.exchange = ccxt.binance({
                'apiKey': config.TESTNET_API_KEY,
                'secret': config.TESTNET_API_SECRET,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',
                    'testnet': True,
                }
            })
            self.exchange.set_sandbox_mode(True)
        else:
            self.exchange = ccxt.binance({
                'apiKey': config.API_KEY,
                'secret': config.SECRET_KEY,
                'enableRateLimit': True,
            })

        self.use_database = use_database
        self.db = OHLCVDatabase() if use_database else None

    def fetch_ohlcv(self, symbol, timeframe='1h', since=None, limit=1000):
        """
        Fetch OHLCV data from Binance

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframe: Candle timeframe (1m, 5m, 15m, 1h, 4h, 1d, 1w)
            since: Start timestamp in milliseconds (if None, fetches recent data)
            limit: Max candles per request (Binance limit is 1000)

        Returns:
            DataFrame with OHLCV data
        """
        try:
            all_ohlcv = []

            while True:
                try:
                    ohlcv = self.exchange.fetch_ohlcv(
                        symbol,
                        timeframe=timeframe,
                        since=since,
                        limit=limit
                    )

                    if not ohlcv:
                        break

                    all_ohlcv.extend(ohlcv)

                    # Update since to last candle time + 1
                    since = ohlcv[-1][0] + 1

                    # Stop if we've reached current time
                    if ohlcv[-1][0] >= self.exchange.milliseconds():
                        break

                    # Rate limiting
                    time.sleep(self.exchange.rateLimit / 1000)

                    # Break if we got less than requested (end of data)
                    if len(ohlcv) < limit:
                        break

                except Exception as e:
                    print(f"Error fetching batch: {e}")
                    break

            if not all_ohlcv:
                return pd.DataFrame()

            # Convert to DataFrame
            df = pd.DataFrame(
                all_ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )

            # Convert timestamp to datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)

            # Convert to numeric
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])

            return df

        except Exception as e:
            print(f"Error fetching {symbol} {timeframe}: {e}")
            return pd.DataFrame()

    def get_or_update(self, symbol, timeframe, days_back=180, max_age_hours=1, force_refresh=False):
        """
        Get data from database or download if missing/stale

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframe: Candle timeframe
            days_back: Days of historical data to fetch initially
            max_age_hours: Maximum age before data is considered stale
            force_refresh: If True, download all data fresh

        Returns:
            DataFrame with OHLCV data
        """
        if not self.use_database:
            # Fallback to old behavior
            return self._fetch_all(symbol, timeframe, days_back)

        # Check if force refresh
        if force_refresh:
            print(f"🔄 Force refresh: {symbol} {timeframe}")
            self.db.delete_data(symbol, timeframe)
            df = self._fetch_all(symbol, timeframe, days_back)
            if not df.empty:
                self.db.save_ohlcv(df, symbol, timeframe)
            return df

        # Check if data exists and is fresh
        metadata = self.db.get_metadata(symbol, timeframe)

        if metadata is None:
            # No data exists - download all
            print(f"📥 Downloading initial data: {symbol} {timeframe}")
            df = self._fetch_all(symbol, timeframe, days_back)
            if not df.empty:
                self.db.save_ohlcv(df, symbol, timeframe)
            return df

        # Data exists - check if it needs updating
        needs_update = self.db.needs_update(symbol, timeframe, max_age_hours)

        if not needs_update:
            # Data is fresh - load from database
            print(f"✓ Loading from database (fresh): {symbol} {timeframe} ({metadata['num_candles']} candles)")
            return self.db.load_ohlcv(symbol, timeframe)

        # Data is stale - fetch new candles only
        print(f"🔄 Updating stale data: {symbol} {timeframe}")
        last_timestamp = self.db.get_last_timestamp(symbol, timeframe)

        # Fetch only new candles since last timestamp
        new_df = self.fetch_ohlcv(symbol, timeframe, since=last_timestamp + 1)

        if not new_df.empty:
            print(f"✓ Downloaded {len(new_df)} new candles")
            self.db.save_ohlcv(new_df, symbol, timeframe)
        else:
            print(f"✓ No new candles available")

        # Return full data from database
        return self.db.load_ohlcv(symbol, timeframe)

    def _fetch_all(self, symbol, timeframe, days_back):
        """Fetch all historical data"""
        since = self.exchange.parse8601(
            (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d %H:%M:%S')
        )

        print(f"Fetching {symbol} {timeframe} ({days_back} days)...")
        df = self.fetch_ohlcv(symbol, timeframe, since=since)

        if not df.empty:
            print(f"✓ Fetched {len(df)} candles")

        return df

    def download_all_configured(self, force_refresh=False):
        """Download all configured assets and timeframes"""
        print("=" * 70)
        print("DOWNLOADING/UPDATING BINANCE DATA")
        print("=" * 70)
        print(f"Database: {'ENABLED' if self.use_database else 'DISABLED'}")
        print(f"Force Refresh: {force_refresh}")
        print("=" * 70)

        total = 0
        for asset in config.CRYPTO_ASSETS:
            # Convert to CCXT format
            if asset.endswith('USDT'):
                symbol = f"{asset[:-4]}/USDT"
            else:
                symbol = asset

            for timeframe in config.CRYPTO_INTERVALS:
                df = self.get_or_update(
                    symbol,
                    timeframe,
                    days_back=config.CRYPTO_LOOKBACK_DAYS,
                    max_age_hours=1,  # Update if older than 1 hour
                    force_refresh=force_refresh
                )

                if not df.empty:
                    total += len(df)

                time.sleep(0.5)  # Be nice to API

        print("\n" + "=" * 70)
        print(f"✓ DOWNLOAD COMPLETE - Total candles: {total:,}")
        print("=" * 70)

        if self.use_database:
            stats = self.db.get_stats()
            print(f"\nDatabase Stats:")
            print(f"  Total Candles: {stats['total_candles']:,}")
            print(f"  Total Pairs: {stats['total_pairs']}")

    def close(self):
        """Close database connection"""
        if self.db:
            self.db.close()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


def download_all_data(force_refresh=False):
    """Download/update all configured assets"""
    with BinanceDataFetcherV2(use_testnet=False, use_database=True) as fetcher:
        fetcher.download_all_configured(force_refresh=force_refresh)


if __name__ == "__main__":
    import sys

    force = '--force' in sys.argv

    if force:
        print("⚠️  FORCE REFRESH MODE - Will re-download all data")

    download_all_data(force_refresh=force)
