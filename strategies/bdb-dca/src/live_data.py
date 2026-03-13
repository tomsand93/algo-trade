"""
Alpaca crypto market data fetcher for live trading.

Uses CryptoHistoricalDataClient (no auth needed for crypto market data).
Fetches 30-minute bars and converts them to bdb_dca.models.Bar objects.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from .models import Bar

log = logging.getLogger(__name__)

# No auth needed for crypto market data
_data_client = None


def _get_client() -> CryptoHistoricalDataClient:
    global _data_client
    if _data_client is None:
        _data_client = CryptoHistoricalDataClient()
    return _data_client


def _alpaca_bar_to_bar(alpaca_bar) -> Bar:
    """Convert a single Alpaca bar to our Bar dataclass."""
    ts = alpaca_bar.timestamp
    if hasattr(ts, 'timestamp'):
        ts_ms = int(ts.timestamp() * 1000)
    else:
        ts_ms = int(ts)
    return Bar(
        timestamp=ts_ms,
        open=float(alpaca_bar.open),
        high=float(alpaca_bar.high),
        low=float(alpaca_bar.low),
        close=float(alpaca_bar.close),
        volume=float(alpaca_bar.volume),
    )


def fetch_warmup_bars(symbol: str = "BTC/USD",
                      days: int = 90) -> list[Bar]:
    """Fetch historical 30m bars for indicator warmup.

    Args:
        symbol: Alpaca crypto symbol (e.g. "BTC/USD")
        days: Number of days of history to fetch

    Returns:
        List of Bar objects sorted by timestamp ascending.
    """
    client = _get_client()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    log.info("Fetching %d days of warmup bars for %s (%s to %s)",
             days, symbol, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))

    req = CryptoBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame(30, TimeFrameUnit.Minute),
        start=start,
        end=end,
    )
    barset = client.get_crypto_bars(req)

    # barset is keyed by symbol
    raw_bars = barset[symbol] if symbol in barset else []
    bars = [_alpaca_bar_to_bar(b) for b in raw_bars]
    bars.sort(key=lambda b: b.timestamp)

    log.info("Fetched %d warmup bars (first: %s, last: %s)",
             len(bars),
             datetime.fromtimestamp(bars[0].timestamp / 1000, tz=timezone.utc).isoformat() if bars else "N/A",
             datetime.fromtimestamp(bars[-1].timestamp / 1000, tz=timezone.utc).isoformat() if bars else "N/A")
    return bars


def fetch_latest_bars(symbol: str = "BTC/USD",
                      count: int = 3) -> list[Bar]:
    """Fetch the most recent completed 30m bars.

    Fetches a small window of recent bars so we can detect the latest
    completed bar (the one whose close time is in the past).

    Args:
        symbol: Alpaca crypto symbol
        count: Number of recent bars to fetch (a small buffer)

    Returns:
        List of Bar objects sorted by timestamp ascending.
    """
    client = _get_client()
    end = datetime.now(timezone.utc)
    # Fetch enough history to get `count` bars plus a buffer
    start = end - timedelta(minutes=30 * (count + 2))

    req = CryptoBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame(30, TimeFrameUnit.Minute),
        start=start,
        end=end,
    )
    barset = client.get_crypto_bars(req)
    raw_bars = barset[symbol] if symbol in barset else []
    bars = [_alpaca_bar_to_bar(b) for b in raw_bars]
    bars.sort(key=lambda b: b.timestamp)
    return bars


def get_last_completed_bar(symbol: str = "BTC/USD") -> Optional[Bar]:
    """Return the most recently completed 30m bar.

    A bar is "completed" if its period end (timestamp + 30min) is
    in the past.
    """
    bars = fetch_latest_bars(symbol, count=5)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    bar_duration_ms = 30 * 60 * 1000  # 30 minutes

    completed = [b for b in bars if b.timestamp + bar_duration_ms <= now_ms]
    if not completed:
        return None
    return completed[-1]
