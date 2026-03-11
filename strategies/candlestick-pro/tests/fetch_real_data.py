"""
Fetch REAL historical data from Binance for backtesting.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import Candle
from src.data_fetcher import DataFetcher
from datetime import datetime, timedelta

# Initialize fetcher
fetcher = DataFetcher(exchange_id="binance", testnet=False)

print("Fetching REAL BTC/USDT historical data from Binance...")
print("="*60)

# Fetch multiple timeframes
timeframes = ['1h', '4h', '1d']
all_data = {}

for tf in timeframes:
    print(f"\nFetching {tf} data...")

    # Get last 1000 candles
    candles = fetcher.fetch_candles('BTC/USDT', tf, limit=1000)

    if candles:
        all_data[tf] = candles
        print(f"  [OK] Fetched {len(candles)} candles")
        print(f"       Date range: {candles[0].datetime} to {candles[-1].datetime}")
        print(f"       Price range: ${min(c.low for c in candles):.2f} - ${max(c.high for c in candles):.2f}")

        # Save to CSV
        filename = f'data/btc_usdt_{tf}_real.csv'
        fetcher.save_to_csv(candles, filename)
    else:
        print(f"  [FAIL] Failed to fetch {tf} data")

print(f"\n" + "="*60)
print(f"Data saved to data/ directory")
print(f"Timeframes available: {list(all_data.keys())}")
