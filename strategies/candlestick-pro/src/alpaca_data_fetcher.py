"""
Alpaca Data Fetcher for Stock Backtesting (New SDK)

Fetches historical 1-minute bar data for US stocks using Alpaca Market Data API.
Uses the modern alpaca-py SDK (not the deprecated alpaca-backtrader-api).

Requires: pip install alpaca-py

Free tier includes:
- Unlimited historical data for stocks
- Real-time and historical data
- No rate limits for paper trading

Get your API keys at: https://alpaca.markets/
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta, timezone
from typing import List, Optional
import pandas as pd

try:
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    from alpaca.data.enums import Adjustment
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    print("[WARNING] alpaca-py not available.")
    print("          Install with: pip install alpaca-py")


from src.models import Candle


class AlpacaDataFetcher:
    """
    Fetch historical stock data from Alpaca for backtesting.

    Uses the modern alpaca-py SDK (not alpaca-backtrader-api).

    Usage:
        fetcher = AlpacaDataFetcher(
            api_key="your-key",
            api_secret="your-secret"
        )

        candles = fetcher.fetch_candles("AAPL", "1m", limit=1000)
    """

    # Timeframe mapping
    TIMEFRAMES = {
        "1m": TimeFrame.Minute,
        "5m": TimeFrame(5, TimeFrameUnit.Minute),
        "15m": TimeFrame(15, TimeFrameUnit.Minute),
        "1h": TimeFrame.Hour,
        "1d": TimeFrame.Day,
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None
    ):
        """
        Initialize Alpaca data fetcher.

        Args:
            api_key: Alpaca API key (or set ALPACA_API_KEY env var)
            api_secret: Alpaca API secret (or set ALPACA_API_SECRET env var)
        """
        if not ALPACA_AVAILABLE:
            raise ImportError("alpaca-py not installed. Run: pip install alpaca-py")

        # Try environment variables if keys not provided
        import os
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.api_secret = api_secret or os.getenv("ALPACA_API_SECRET")

        if not self.api_key or not self.api_secret:
            raise ValueError(
                "Alpaca API keys required. Either:\n"
                "  1. Pass api_key and api_secret parameters\n"
                "  2. Set ALPACA_API_KEY and ALPACA_API_SECRET environment variables\n"
                "Get keys at: https://alpaca.markets/"
            )

        # Initialize Alpaca data client
        self.client = StockHistoricalDataClient(
            api_key=self.api_key,
            secret_key=self.api_secret
        )

        print(f"[Alpaca] Initialized with alpaca-py SDK")

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 1000,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> List[Candle]:
        """
        Fetch historical candles for a stock symbol.

        Args:
            symbol: Stock symbol (e.g., "AAPL", "TSLA")
            timeframe: Timeframe ("1m", "5m", "15m", "1h", "1d")
            limit: Maximum number of candles to fetch
            start: Start datetime (optional, defaults to most recent)
            end: End datetime (optional)

        Returns:
            List of Candle objects
        """
        if timeframe not in self.TIMEFRAMES:
            raise ValueError(f"Invalid timeframe. Use one of: {list(self.TIMEFRAMES.keys())}")

        alpaca_tf = self.TIMEFRAMES[timeframe]

        # Default to recent data if not specified
        if end is None:
            end = datetime.now(timezone.utc)
        if start is None:
            # Calculate start based on limit and timeframe
            # Alpaca provides data for trading days only (6.5 hours/day = 390 minutes)
            minutes_per_day = 390

            if timeframe == "1m":
                days_needed = min((limit // minutes_per_day) + 5, 30)  # Cap at 30 days
            elif timeframe == "5m":
                days_needed = min(((limit * 5) // minutes_per_day) + 5, 60)
            elif timeframe == "15m":
                days_needed = min(((limit * 15) // minutes_per_day) + 5, 90)
            elif timeframe == "1h":
                days_needed = min((limit // 6) + 5, 180)
            else:  # 1d
                days_needed = min(limit + 30, 365)

            start = end - timedelta(days=days_needed)

        print(f"[Alpaca] Fetching {symbol} {timeframe} data...")
        print(f"         Start: {start.strftime('%Y-%m-%d %H:%M')}")
        print(f"         End:   {end.strftime('%Y-%m-%d %H:%M')}")

        try:
            # Create request - use IEX feed (free tier) instead of SIP
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=alpaca_tf,
                start=start,
                end=end,
                adjustment=Adjustment.RAW,  # Use raw prices (no adjustments)
                feed="iex"  # Use IEX feed (available on free tier)
            )

            # Fetch bars from Alpaca
            response = self.client.get_stock_bars(request)

            if not response or symbol not in response.data:
                print(f"[Alpaca] No data returned for {symbol}")
                return []

            # Get bars for the symbol
            bars = response.data[symbol]

            # Convert to list and limit
            bars_list = list(bars)[-limit:]  # Get most recent N bars

            if not bars_list:
                print(f"[Alpaca] No bars returned for {symbol}")
                return []

            # Convert Alpaca bars to our Candle model
            candles = []
            for bar in bars_list:
                candle = Candle(
                    timestamp=int(bar.timestamp.timestamp() * 1000),  # Convert to milliseconds
                    open=float(bar.open),
                    high=float(bar.high),
                    low=float(bar.low),
                    close=float(bar.close),
                    volume=float(bar.volume)
                )
                candles.append(candle)

            print(f"[Alpaca] Fetched {len(candles)} candles for {symbol}")
            if candles:
                from datetime import datetime as dt
                start_dt = dt.fromtimestamp(candles[0].timestamp / 1000)
                end_dt = dt.fromtimestamp(candles[-1].timestamp / 1000)
                print(f"         Range: {start_dt} to {end_dt}")

            return candles

        except Exception as e:
            print(f"[Alpaca] Error fetching {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return []

    def fetch_multi_timeframe(
        self,
        symbol: str,
        timeframes: List[str],
        limit: int = 1000
    ) -> dict:
        """
        Fetch multiple timeframes for a symbol.

        Args:
            symbol: Stock symbol
            timeframes: List of timeframes ("1m", "15m", etc.)
            limit: Max candles per timeframe

        Returns:
            Dict with timeframe as key, list of candles as value
        """
        result = {}
        for tf in timeframes:
            result[tf] = self.fetch_candles(symbol, tf, limit)
        return result


# =============================================================================
# STOCK ASSETS FOR TESTING
# =============================================================================

# Large-cap tech stocks (high volume, good for 1-minute trading)
LARGE_CAP_STOCKS = [
    {"symbol": "AAPL", "name": "Apple Inc"},
    {"symbol": "MSFT", "name": "Microsoft"},
    {"symbol": "GOOGL", "name": "Google (Alphabet)"},
    {"symbol": "TSLA", "name": "Tesla"},
    {"symbol": "NVDA", "name": "NVIDIA"},
    {"symbol": "AMZN", "name": "Amazon"},
    {"symbol": "META", "name": "Meta Platforms"},
    {"symbol": "AMD", "name": "Advanced Micro Devices"},
]

# High-volatility stocks
VOLATILE_STOCKS = [
    {"symbol": "COIN", "name": "Coinbase"},
    {"symbol": "SQ", "name": "Block (Square)"},
    {"symbol": "HOOD", "name": "Robinhood"},
    {"symbol": "PLTR", "name": "Palantir"},
]

# ETFs for broader market exposure
ETF_LIST = [
    {"symbol": "SPY", "name": "S&P 500 ETF"},
    {"symbol": "QQQ", "name": "Nasdaq 100 ETF"},
    {"symbol": "IWM", "name": "Russell 2000 ETF"},
]


# =============================================================================
# TEST ALPACA CONNECTION
# =============================================================================

def test_alpaca_connection():
    """Test Alpaca API connection and fetch sample data."""
    print("=" * 70)
    print("ALPACA DATA FETCHER TEST (alpaca-py SDK)")
    print("=" * 70)

    if not ALPACA_AVAILABLE:
        print("\n[ERROR] alpaca-py not installed")
        print("Install with: pip install alpaca-py")
        return False

    try:
        fetcher = AlpacaDataFetcher()

        # Test fetching AAPL 1-minute data
        print("\nTesting AAPL 1-minute data fetch...")
        candles = fetcher.fetch_candles("AAPL", "1m", limit=100)

        if candles:
            print(f"\n[SUCCESS] Fetched {len(candles)} candles")
            print(f"  First: {candles[0].datetime} | O: {candles[0].open:.2f} H: {candles[0].high:.2f} L: {candles[0].low:.2f} C: {candles[0].close:.2f}")
            print(f"  Last:  {candles[-1].datetime} | O: {candles[-1].open:.2f} H: {candles[-1].high:.2f} L: {candles[-1].low:.2f} C: {candles[-1].close:.2f}")
            return True
        else:
            print("[FAILED] No candles returned")
            return False

    except ValueError as e:
        print(f"\n[CONFIG ERROR] {e}")
        print("\nTo use Alpaca data:")
        print("  1. Create free account at https://alpaca.markets/")
        print("  2. Get API keys from dashboard")
        print("  3. Set environment variables:")
        print("     set ALPACA_API_KEY=your-key-here")
        print("     set ALPACA_API_SECRET=your-secret-here")
        return False
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_alpaca_connection()
