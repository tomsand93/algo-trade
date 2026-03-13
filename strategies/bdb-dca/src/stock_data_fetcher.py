"""
Fetch US stock OHLCV data from Alpaca with CSV caching.

Uses StockHistoricalDataClient (requires ALPACA_API_KEY and
ALPACA_API_SECRET environment variables).
Fetches 30-minute bars with split adjustment.
"""

import os
from datetime import datetime, timezone

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import Adjustment, DataFeed

from .models import Bar


_data_client = None


def _get_client() -> StockHistoricalDataClient:
    global _data_client
    if _data_client is None:
        api_key = os.environ.get("ALPACA_API_KEY") or os.environ.get("APCA_API_KEY_ID")
        api_secret = os.environ.get("ALPACA_API_SECRET") or os.environ.get("APCA_API_SECRET_KEY")
        if not api_key or not api_secret:
            raise RuntimeError(
                "Set ALPACA_API_KEY and ALPACA_API_SECRET env vars "
                "for Alpaca stock data access"
            )
        _data_client = StockHistoricalDataClient(api_key, api_secret)
    return _data_client


def fetch_stock_bars(symbol: str, start_date: str, end_date: str,
                     cache_dir: str = "data") -> list[Bar]:
    """
    Fetch 30-minute stock bars from Alpaca with CSV caching.

    Args:
        symbol: Stock ticker (e.g. "AAPL", "SPY")
        start_date: Start date "YYYY-MM-DD"
        end_date: End date "YYYY-MM-DD"
        cache_dir: Directory for CSV cache files

    Returns:
        List of Bar objects sorted by timestamp ascending.
    """
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"{symbol}_30m_stock.csv")

    start_ms = _date_to_ms(start_date)
    end_ms = _date_to_ms(end_date)

    # Check if cache exists and covers our range
    # Tolerance: 3 days for start (weekends), 1 day for end (market close)
    _3_DAYS_MS = 3 * 86400 * 1000
    _1_DAY_MS = 86400 * 1000
    if os.path.exists(cache_file):
        df = pd.read_csv(cache_file)
        if len(df) > 0:
            cached_start = df['timestamp'].min()
            cached_end = df['timestamp'].max()
            if (cached_start <= start_ms + _3_DAYS_MS
                    and cached_end >= end_ms - _1_DAY_MS):
                df = df[(df['timestamp'] >= start_ms) & (df['timestamp'] <= end_ms)]
                return _df_to_bars(df)

    # Fetch from Alpaca
    print(f"Fetching {symbol} 30m stock bars from Alpaca...")
    client = _get_client()

    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame(30, TimeFrameUnit.Minute),
        start=start_dt,
        end=end_dt,
        adjustment=Adjustment.SPLIT,
        feed=DataFeed.IEX,
    )
    barset = client.get_stock_bars(req)

    # barset.data is keyed by symbol
    raw_bars = barset.data.get(symbol, [])

    if not raw_bars:
        raise ValueError(f"No data fetched for {symbol}")

    # Convert to DataFrame for caching
    rows = []
    for b in raw_bars:
        ts = b.timestamp
        if hasattr(ts, 'timestamp'):
            ts_ms = int(ts.timestamp() * 1000)
        else:
            ts_ms = int(ts)
        rows.append({
            'timestamp': ts_ms,
            'open': float(b.open),
            'high': float(b.high),
            'low': float(b.low),
            'close': float(b.close),
            'volume': float(b.volume),
        })

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)
    df.to_csv(cache_file, index=False)
    print(f"Cached {len(df)} bars to {cache_file}")

    # Filter to requested range
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
