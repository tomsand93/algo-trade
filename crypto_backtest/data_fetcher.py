"""
Binance Data Fetcher with Smart Incremental Updates

Features:
- Downloads OHLCV data from Binance
- Stores in SQLite database
- Only downloads NEW candles (incremental updates)
- Automatic staleness detection
"""
import ccxt
import pandas as pd
from datetime import datetime, timedelta
import time
from database import OHLCVDatabase
import config


class BinanceDataFetcher:
    """Smart data fetcher with incremental updates"""

    def __init__(self, use_testnet=False):
        """
        Initialize Binance connection

        Args:
            use_testnet: Use testnet credentials if True
        """
        # Initialize exchange
        if use_testnet:
            api_key = config.BINANCE_TESTNET_API_KEY
            secret = config.BINANCE_TESTNET_SECRET_KEY
        else:
            api_key = config.BINANCE_API_KEY
            secret = config.BINANCE_SECRET_KEY

        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': secret,
            'enableRateLimit': True,
        })

        if use_testnet:
            self.exchange.set_sandbox_mode(True)

        # Initialize database
        self.db = OHLCVDatabase()

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=1000):
        """
        Fetch OHLCV data from Binance

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframe: Candle timeframe (e.g., '1h')
            since: Start timestamp in milliseconds
            limit: Max candles per request

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

                    # Update since to last candle + 1
                    since = ohlcv[-1][0] + 1

                    # Stop if reached current time
                    if ohlcv[-1][0] >= self.exchange.milliseconds():
                        break

                    # Rate limiting
                    time.sleep(self.exchange.rateLimit / 1000)

                    # Break if less than requested
                    if len(ohlcv) < limit:
                        break

                except Exception as e:
                    print(f"  Error fetching batch: {e}")
                    break

            if not all_ohlcv:
                return pd.DataFrame()

            # Convert to DataFrame
            df = pd.DataFrame(
                all_ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )

            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)

            # Convert to numeric
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])

            return df

        except Exception as e:
            print(f"  Error fetching {symbol} {timeframe}: {e}")
            return pd.DataFrame()

    def get_or_update(self, symbol, timeframe, force_refresh=False):
        """
        Get data from database or download if needed

        This is the SMART function that handles incremental updates!

        Args:
            symbol: Trading pair
            timeframe: Candle timeframe
            force_refresh: Force re-download all data

        Returns:
            DataFrame with OHLCV data
        """
        # Force refresh - delete and re-download
        if force_refresh:
            print(f"🔄 Force refresh: {symbol} {timeframe}")
            self.db.delete_data(symbol, timeframe)
            df = self._fetch_all(symbol, timeframe)
            if not df.empty:
                self.db.save_ohlcv(df, symbol, timeframe)
            return df

        # Check if data exists
        metadata = self.db.get_metadata(symbol, timeframe)

        if metadata is None:
            # No data - download all
            print(f"📥 Initial download: {symbol} {timeframe}")
            df = self._fetch_all(symbol, timeframe)
            if not df.empty:
                self.db.save_ohlcv(df, symbol, timeframe)
            return df

        # Data exists - check if stale
        needs_update = self.db.needs_update(symbol, timeframe, config.MAX_DATA_AGE_HOURS)

        if not needs_update:
            # Data is fresh - load from database
            print(f"✓ Using cached data: {symbol} {timeframe} ({metadata['num_candles']} candles)")
            return self.db.load_ohlcv(symbol, timeframe)

        # Data is stale - fetch only NEW candles
        print(f"🔄 Updating: {symbol} {timeframe}", end=" ")
        last_timestamp = self.db.get_last_timestamp(symbol, timeframe)

        # Fetch new candles since last timestamp
        new_df = self.fetch_ohlcv(symbol, timeframe, since=last_timestamp + 1)

        if not new_df.empty:
            print(f"(+{len(new_df)} new candles)")
            self.db.save_ohlcv(new_df, symbol, timeframe)
        else:
            print("(no new candles)")

        # Return full dataset
        return self.db.load_ohlcv(symbol, timeframe)

    def _fetch_all(self, symbol, timeframe):
        """Fetch all historical data"""
        since = self.exchange.parse8601(
            (datetime.now() - timedelta(days=config.LOOKBACK_DAYS)).strftime('%Y-%m-%d %H:%M:%S')
        )

        df = self.fetch_ohlcv(symbol, timeframe, since=since)

        if not df.empty:
            print(f"  Downloaded {len(df)} candles")

        return df

    def download_all_configured(self, force_refresh=False):
        """Download/update all configured assets and timeframes"""
        print("=" * 70)
        print("BINANCE DATA DOWNLOAD/UPDATE")
        print("=" * 70)
        print(f"Mode: {'FORCE REFRESH' if force_refresh else 'SMART UPDATE'}")
        print(f"Assets: {len(config.CRYPTO_ASSETS)}")
        print(f"Timeframes: {len(config.CRYPTO_INTERVALS)}")
        print("=" * 70)

        total_candles = 0
        for asset in config.CRYPTO_ASSETS:
            # Convert to CCXT format
            if asset.endswith('USDT'):
                symbol = f"{asset[:-4]}/USDT"
            else:
                symbol = asset

            for timeframe in config.CRYPTO_INTERVALS:
                df = self.get_or_update(symbol, timeframe, force_refresh)

                if not df.empty:
                    total_candles += len(df)

                time.sleep(0.5)  # Rate limiting

        print("\n" + "=" * 70)
        print(f"✓ COMPLETE - Total candles available: {total_candles:,}")
        print("=" * 70)

        # Show database stats
        stats = self.db.get_stats()
        print(f"\n📊 Database Stats:")
        print(f"  Total Candles: {stats['total_candles']:,}")
        print(f"  Total Pairs: {stats['total_pairs']}")
        print(f"  Database Size: {stats['db_size_mb']:.2f} MB")

    def close(self):
        """Close database connection"""
        self.db.close()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


def download_data(force=False):
    """Main function to download/update data"""
    with BinanceDataFetcher(use_testnet=False) as fetcher:
        fetcher.download_all_configured(force_refresh=force)


if __name__ == "__main__":
    import sys
    force = '--force' in sys.argv

    if force:
        print("⚠️  FORCE REFRESH MODE\n")

    download_data(force=force)
