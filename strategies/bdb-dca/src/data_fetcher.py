"""
Fetch OHLCV data from Binance via ccxt with CSV caching.
"""

import os
import time
from datetime import datetime, timezone

import ccxt
import pandas as pd

from .models import Bar


def fetch_ohlcv(symbol: str, timeframe: str, start_date: str, end_date: str,
                cache_dir: str = "data") -> list[Bar]:
    """
    Fetch OHLCV from Binance, paginating 1000 bars at a time.
    Caches result to CSV. Returns list of Bar objects.
    """
    os.makedirs(cache_dir, exist_ok=True)
    safe_symbol = symbol.replace("/", "")
    cache_file = os.path.join(cache_dir, f"{safe_symbol}_{timeframe}.csv")

    start_ms = _date_to_ms(start_date)
    end_ms = _date_to_ms(end_date)

    # Check if cache exists and covers our range
    if os.path.exists(cache_file):
        df = pd.read_csv(cache_file)
        if len(df) > 0:
            cached_start = df['timestamp'].min()
            cached_end = df['timestamp'].max()
            if cached_start <= start_ms and cached_end >= end_ms - 1800000:
                # Filter to our range
                df = df[(df['timestamp'] >= start_ms) & (df['timestamp'] <= end_ms)]
                return _df_to_bars(df)

    # Fetch from exchange
    print(f"Fetching {symbol} {timeframe} from Binance...")
    exchange = ccxt.binance({'enableRateLimit': True})

    all_candles = []
    since = start_ms
    limit = 1000

    while since < end_ms:
        candles = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
        if not candles:
            break

        all_candles.extend(candles)
        last_ts = candles[-1][0]

        if last_ts >= end_ms or len(candles) < limit:
            break

        since = last_ts + 1
        time.sleep(exchange.rateLimit / 1000)

    if not all_candles:
        raise ValueError(f"No data fetched for {symbol} {timeframe}")

    # Build DataFrame and cache
    df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df = df.drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)
    df.to_csv(cache_file, index=False)
    print(f"Cached {len(df)} bars to {cache_file}")

    # Filter to range
    df = df[(df['timestamp'] >= start_ms) & (df['timestamp'] <= end_ms)]
    return _df_to_bars(df)


def _date_to_ms(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _df_to_bars(df: pd.DataFrame) -> list[Bar]:
    bars = []
    for _, row in df.iterrows():
        bars.append(Bar(
            timestamp=int(row['timestamp']),
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close']),
            volume=float(row['volume']),
        ))
    return bars
