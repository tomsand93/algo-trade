"""
Data fetcher for Binance using CCXT
Supports all timeframes: 1m, 5m, 15m, 1h, 4h, 1d, 1w
"""
import ccxt
import pandas as pd
from datetime import datetime, timedelta
import time
from pathlib import Path
import config


class BinanceDataFetcher:
    """Fetch historical OHLCV data from Binance"""

    def __init__(self, use_testnet=True):
        """
        Initialize Binance connection

        Args:
            use_testnet: If True, use testnet credentials
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

    def fetch_ohlcv(self, symbol, timeframe='1h', days_back=180, limit=1000):
        """
        Fetch OHLCV data from Binance

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframe: Candle timeframe (1m, 5m, 15m, 1h, 4h, 1d, 1w)
            days_back: Number of days of historical data
            limit: Max candles per request (Binance limit is 1000)

        Returns:
            DataFrame with OHLCV data
        """
        try:
            print(f"Fetching {symbol} {timeframe} data...")

            # Calculate since timestamp
            since = self.exchange.parse8601(
                (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d %H:%M:%S')
            )

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
                print(f"No data fetched for {symbol} {timeframe}")
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

            print(f"✓ Fetched {len(df)} candles for {symbol} {timeframe}")
            return df

        except Exception as e:
            print(f"Error fetching {symbol} {timeframe}: {e}")
            return pd.DataFrame()

    def save_to_csv(self, df, symbol, timeframe):
        """Save DataFrame to CSV file"""
        if df.empty:
            return

        config.DATA_DIR.mkdir(exist_ok=True)

        # Clean symbol for filename (remove /)
        clean_symbol = symbol.replace('/', '_')
        filename = f"{clean_symbol}_{timeframe}.csv"
        filepath = config.DATA_DIR / filename

        df.to_csv(filepath)
        print(f"Saved to {filepath}")

    def load_from_csv(self, symbol, timeframe):
        """Load DataFrame from CSV file"""
        clean_symbol = symbol.replace('/', '_')
        filename = f"{clean_symbol}_{timeframe}.csv"
        filepath = config.DATA_DIR / filename

        if not filepath.exists():
            return None

        df = pd.read_csv(filepath, index_col='timestamp', parse_dates=True)
        return df

    def fetch_and_save(self, symbol, timeframe, days_back=180, force_refresh=False):
        """
        Fetch data and save to CSV, or load from cache

        Args:
            symbol: Trading pair
            timeframe: Candle timeframe
            days_back: Days of historical data
            force_refresh: If True, fetch fresh data even if cached

        Returns:
            DataFrame with OHLCV data
        """
        if not force_refresh:
            cached_df = self.load_from_csv(symbol, timeframe)
            if cached_df is not None:
                print(f"Loaded {symbol} {timeframe} from cache ({len(cached_df)} candles)")
                return cached_df

        df = self.fetch_ohlcv(symbol, timeframe, days_back)

        if not df.empty:
            self.save_to_csv(df, symbol, timeframe)

        return df


def download_all_data():
    """Download all configured assets and timeframes"""
    fetcher = BinanceDataFetcher(use_testnet=False)

    print("=" * 60)
    print("DOWNLOADING BINANCE DATA")
    print("=" * 60)

    for asset in config.CRYPTO_ASSETS:
        # Convert to CCXT format (BTC/USDT instead of BTCUSDT)
        if asset.endswith('USDT'):
            symbol = f"{asset[:-4]}/USDT"
        else:
            symbol = asset

        for timeframe in config.CRYPTO_INTERVALS:
            fetcher.fetch_and_save(
                symbol,
                timeframe,
                days_back=config.CRYPTO_LOOKBACK_DAYS,
                force_refresh=True
            )
            time.sleep(0.5)  # Be nice to the API

    print("\n" + "=" * 60)
    print("DOWNLOAD COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    download_all_data()
