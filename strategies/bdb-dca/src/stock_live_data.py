"""
Stock market data fetcher for live trading.

Uses yfinance for historical bar data (free, full coverage).
Includes market hours checking (9:30 AM - 4:00 PM ET).
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import yfinance as yf

from .models import Bar

log = logging.getLogger(__name__)


def _yf_row_to_bar(timestamp, row) -> Bar:
    """Convert a yfinance DataFrame row to our Bar dataclass."""
    ts_ms = int(timestamp.timestamp() * 1000)
    return Bar(
        timestamp=ts_ms,
        open=float(row['Open']),
        high=float(row['High']),
        low=float(row['Low']),
        close=float(row['Close']),
        volume=float(row['Volume']),
    )


def _is_market_hours_bar(bar_timestamp_ms: int) -> bool:
    """Check if bar falls within regular market hours (9:30 AM - 4:00 PM ET).

    Bar timestamp is the start of the bar period. A 9:30 AM bar covers 9:30-10:00.
    """
    dt = datetime.fromtimestamp(bar_timestamp_ms / 1000, tz=timezone.utc)
    # Convert to ET (UTC-5 or UTC-4 during DST)
    # Simple approach: check if hour is between 14:30 and 20:00 UTC (9:30-4:00 ET standard)
    # This is approximate but works for most cases
    try:
        import zoneinfo
        et = zoneinfo.ZoneInfo("America/New_York")
    except ImportError:
        # Fallback for Python < 3.9
        from datetime import timezone as tz
        et = tz(timedelta(hours=-5))  # EST (doesn't account for DST)

    dt_et = dt.astimezone(et)
    market_open = dt_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = dt_et.replace(hour=16, minute=0, second=0, microsecond=0)

    # Bar must start at or after 9:30 and before 16:00 (last bar is 15:30)
    return market_open <= dt_et < market_close


def is_market_open() -> bool:
    """Check if US stock market is currently open.

    Returns True if current time is between 9:30 AM and 4:00 PM ET on a weekday.
    Does not account for holidays.
    """
    now = datetime.now(timezone.utc)
    try:
        import zoneinfo
        et = zoneinfo.ZoneInfo("America/New_York")
    except ImportError:
        from datetime import timezone as tz
        et = tz(timedelta(hours=-5))

    now_et = now.astimezone(et)

    # Check if weekday (Monday = 0, Friday = 4)
    if now_et.weekday() > 4:
        return False

    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)

    return market_open <= now_et < market_close


def get_next_market_open() -> datetime:
    """Return the next market open time in UTC."""
    now = datetime.now(timezone.utc)
    try:
        import zoneinfo
        et = zoneinfo.ZoneInfo("America/New_York")
    except ImportError:
        from datetime import timezone as tz
        et = tz(timedelta(hours=-5))

    now_et = now.astimezone(et)
    next_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)

    # If already past 9:30 today, try tomorrow
    if now_et >= next_open:
        next_open += timedelta(days=1)

    # Skip weekends
    while next_open.weekday() > 4:
        next_open += timedelta(days=1)

    return next_open.astimezone(timezone.utc)


def fetch_stock_warmup_bars(symbol: str, days: int = 90) -> list[Bar]:
    """Fetch historical 30m bars for indicator warmup using yfinance.

    Args:
        symbol: Stock symbol (e.g. "AAPL")
        days: Number of days of history to fetch (capped at 59 for 30m bars)

    Returns:
        List of Bar objects sorted by timestamp ascending.
        Only includes bars from regular market hours.
    """
    # yfinance 30m bars limited to ~60 days
    period_days = min(days, 59)
    log.info("Fetching %d days of warmup bars for %s via yfinance", period_days, symbol)

    ticker = yf.Ticker(symbol)
    df = ticker.history(period=f"{period_days}d", interval="30m")

    if df.empty:
        log.warning("yfinance returned no data for %s", symbol)
        return []

    bars = []
    for ts, row in df.iterrows():
        bar = _yf_row_to_bar(ts, row)
        if _is_market_hours_bar(bar.timestamp):
            bars.append(bar)

    bars.sort(key=lambda b: b.timestamp)

    log.info("Fetched %d warmup bars (first: %s, last: %s)",
             len(bars),
             datetime.fromtimestamp(bars[0].timestamp / 1000, tz=timezone.utc).isoformat() if bars else "N/A",
             datetime.fromtimestamp(bars[-1].timestamp / 1000, tz=timezone.utc).isoformat() if bars else "N/A")
    return bars


def fetch_latest_stock_bars(symbol: str, count: int = 5) -> list[Bar]:
    """Fetch the most recent completed 30m bars using yfinance.

    Args:
        symbol: Stock symbol (e.g. "AAPL")
        count: Number of recent bars to fetch (a small buffer)

    Returns:
        List of Bar objects sorted by timestamp ascending.
        Only includes bars from regular market hours.
    """
    ticker = yf.Ticker(symbol)
    df = ticker.history(period="5d", interval="30m")

    if df.empty:
        return []

    bars = []
    for ts, row in df.iterrows():
        bar = _yf_row_to_bar(ts, row)
        if _is_market_hours_bar(bar.timestamp):
            bars.append(bar)

    bars.sort(key=lambda b: b.timestamp)

    # Return only the last `count` bars
    return bars[-count:] if len(bars) > count else bars


def get_last_completed_stock_bar(symbol: str) -> Optional[Bar]:
    """Return the most recently completed 30m bar during market hours.

    A bar is "completed" if its period end (timestamp + 30min) is
    in the past. Only returns bars from regular market hours.
    """
    bars = fetch_latest_stock_bars(symbol, count=10)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    bar_duration_ms = 30 * 60 * 1000  # 30 minutes

    # Filter to completed bars
    completed = [b for b in bars if b.timestamp + bar_duration_ms <= now_ms]
    if not completed:
        return None
    return completed[-1]
