"""
Price data provider with caching.

Supports:
1. yfinance for backtest data (daily)
2. Alpaca for paper trading and intraday data
3. Local caching to minimize API calls
"""
import os
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any
import json
import pickle

import pandas as pd
import yfinance as yf

from ..normalize.schema import PriceBar

logger = logging.getLogger(__name__)


class PriceCache:
    """Local cache for price data."""

    def __init__(self, cache_dir: str = "data/cache/prices"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _get_cache_path(self, ticker: str, timeframe: str) -> str:
        """Get cache file path for ticker and timeframe."""
        return os.path.join(self.cache_dir, f"{ticker}_{timeframe}.pkl")

    def get(self, ticker: str, timeframe: str) -> Optional[List[PriceBar]]:
        """Get cached price data."""
        path = self._get_cache_path(ticker, timeframe)
        if not os.path.exists(path):
            return None

        try:
            with open(path, "rb") as f:
                data = pickle.load(f)
            logger.debug(f"Loaded {len(data)} bars from cache for {ticker} {timeframe}")
            return data
        except Exception as e:
            logger.warning(f"Failed to load cache for {ticker}: {e}")
            return None

    def set(self, ticker: str, timeframe: str, bars: List[PriceBar]) -> None:
        """Cache price data."""
        path = self._get_cache_path(ticker, timeframe)
        try:
            with open(path, "wb") as f:
                pickle.dump(bars, f)
            logger.debug(f"Cached {len(bars)} bars for {ticker} {timeframe}")
        except Exception as e:
            logger.warning(f"Failed to cache data for {ticker}: {e}")

    def is_fresh(self, ticker: str, timeframe: str, max_age_hours: int = 24) -> bool:
        """Check if cached data is fresh enough."""
        path = self._get_cache_path(ticker, timeframe)
        if not os.path.exists(path):
            return False

        mtime = os.path.getmtime(path)
        age_hours = (time.time() - mtime) / 3600
        return age_hours <= max_age_hours


class YFinanceProvider:
    """
    Price data provider using yfinance.

    Suitable for backtesting with daily data.
    """

    TIMEFRAME_MAP = {
        "1D": "1d",
        "1H": "1h",
        "15m": "15m",
        "5m": "5m",
    }

    def __init__(self, cache: Optional[PriceCache] = None):
        """
        Initialize yfinance provider.

        Args:
            cache: Optional price cache
        """
        self.cache = cache or PriceCache()

    def fetch_bars(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        timeframe: str = "1D"
    ) -> List[PriceBar]:
        """
        Fetch price bars for a ticker and date range.

        Args:
            ticker: Stock ticker
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            timeframe: Timeframe ("1D", "1H", "15m")

        Returns:
            List of PriceBar objects
        """
        # Check cache first
        cached = self.cache.get(ticker, timeframe)
        if cached and self._is_cache_sufficient(cached, start_date, end_date):
            return self._filter_by_date(cached, start_date, end_date)

        # Fetch from yfinance
        yf_interval = self.TIMEFRAME_MAP.get(timeframe, "1d")

        try:
            # yfinance requires datetime for start/end
            start_dt = datetime.combine(start_date, datetime.min.time())
            end_dt = datetime.combine(end_date, datetime.max.time())

            # Add buffer for intraday data
            if timeframe != "1D":
                start_dt = start_dt - timedelta(days=7)

            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(
                start=start_dt.strftime("%Y-%m-%d"),
                end=end_dt.strftime("%Y-%m-%d"),
                interval=yf_interval,
                auto_adjust=False,  # Get raw data
                repair=True,
                keepna=False,
            )

            if df.empty:
                logger.warning(f"No data found for {ticker} from {start_date} to {end_date}")
                return []

            bars = self._df_to_bars(df, timeframe)

            # Update cache
            self.cache.set(ticker, timeframe, bars)

            return self._filter_by_date(bars, start_date, end_date)

        except Exception as e:
            logger.error(f"Failed to fetch yfinance data for {ticker}: {e}")
            return []

    def _df_to_bars(self, df: pd.DataFrame, timeframe: str) -> List[PriceBar]:
        """Convert DataFrame to PriceBar list."""
        bars = []

        for timestamp, row in df.iterrows():
            # Handle timezone
            if pd.isna(timestamp):
                continue

            dt = timestamp.to_pydatetime()

            bars.append(PriceBar(
                datetime=dt,
                open=Decimal(str(row["Open"])),
                high=Decimal(str(row["High"])),
                low=Decimal(str(row["Low"])),
                close=Decimal(str(row["Close"])),
                volume=int(row["Volume"]),
            ))

        return bars

    def _is_cache_sufficient(
        self,
        cached: List[PriceBar],
        start_date: date,
        end_date: date
    ) -> bool:
        """Check if cached data covers the requested range."""
        if not cached:
            return False

        first_date = cached[0].datetime.date()
        last_date = cached[-1].datetime.date()

        return first_date <= start_date and last_date >= end_date

    def _filter_by_date(
        self,
        bars: List[PriceBar],
        start_date: date,
        end_date: date
    ) -> List[PriceBar]:
        """Filter bars by date range."""
        return [
            b for b in bars
            if start_date <= b.datetime.date() <= end_date
        ]

    def get_latest_price(self, ticker: str) -> Optional[Decimal]:
        """Get the latest available price for a ticker."""
        try:
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period="1d", interval="1d")

            if df.empty:
                return None

            return Decimal(str(df["Close"].iloc[-1]))

        except Exception as e:
            logger.error(f"Failed to get latest price for {ticker}: {e}")
            return None

    def get_price_on_date(self, ticker: str, target_date: date) -> Optional[Decimal]:
        """
        Get the closing price for a ticker on a specific date.

        Args:
            ticker: Stock ticker
            target_date: Date to get price for

        Returns:
            Closing price on target date, or None if unavailable
        """
        try:
            # Fetch data around the target date (with buffer)
            start_date = target_date - timedelta(days=5)
            end_date = target_date + timedelta(days=5)

            bars = self.fetch_bars(ticker, start_date, end_date, "1D")

            if not bars:
                return None

            # Find the closest bar to target_date
            for bar in bars:
                if bar.datetime.date() == target_date:
                    return bar.close

            # If no exact match, return closest date's price
            return bars[0].close if bars else None

        except Exception as e:
            logger.error(f"Failed to get price for {ticker} on {target_date}: {e}")
            return None

    def calculate_avg_dollar_volume(
        self,
        ticker: str,
        lookback_days: int = 20,
        end_date: Optional[date] = None
    ) -> Optional[Decimal]:
        """
        Calculate average daily dollar volume.

        Args:
            ticker: Stock ticker
            lookback_days: Number of days to look back
            end_date: End date (default: today)

        Returns:
            Average daily dollar volume or None if unavailable
        """
        end_date = end_date or date.today()
        start_date = end_date - timedelta(days=lookback_days + 10)  # Buffer for non-trading days

        bars = self.fetch_bars(ticker, start_date, end_date, "1D")

        if len(bars) < lookback_days // 2:
            return None

        # Use the most recent `lookback_days` bars
        recent_bars = bars[-lookback_days:]

        total_dvol = sum(
            b.close * Decimal(str(b.volume))
            for b in recent_bars
        )

        return total_dvol / Decimal(str(len(recent_bars)))


class AlpacaPriceProvider:
    """
    Price data provider using Alpaca Market Data API.

    Suitable for paper trading and intraday data.
    """

    BASE_URL = "https://data.alpaca.markets"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        cache: Optional[PriceCache] = None,
        paper: bool = True
    ):
        """
        Initialize Alpaca price provider.

        Args:
            api_key: Alpaca API key
            api_secret: Alpaca API secret
            cache: Optional price cache
            paper: Use paper trading endpoints
        """
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.api_secret = api_secret or os.getenv("ALPACA_API_SECRET")
        self.paper = paper
        self.cache = cache or PriceCache()

        if not self.api_key or not self.api_secret:
            logger.warning("Alpaca credentials not found. Provider will not function.")

        self.session = requests.Session()
        self.session.headers.update({
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
        })

    def fetch_bars(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        timeframe: str = "1D",
        limit: int = 10000
    ) -> List[PriceBar]:
        """Fetch price bars from Alpaca."""
        if not self.api_key or not self.api_secret:
            raise ValueError("Alpaca API credentials required")

        # Check cache
        cached = self.cache.get(ticker, timeframe)
        if cached and self._is_cache_sufficient(cached, start_date, end_date):
            return self._filter_by_date(cached, start_date, end_date)

        # Map timeframe to Alpaca format
        alpaca_tf = {
            "1D": "1Day",
            "1H": "1Hour",
            "15m": "15Min",
            "5m": "5Min",
            "1m": "1Min",
        }.get(timeframe, "1Day")

        # Convert dates to ISO format
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        url = f"{self.BASE_URL}/v2/stocks/{ticker}/bars"
        params = {
            "timeframe": alpaca_tf,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "limit": limit,
            "adjustment": "raw",
        }

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()
            bars_data = data.get("bars", [])

            bars = [
                PriceBar(
                    datetime=datetime.fromisoformat(b["t"].replace("Z", "+00:00")),
                    open=Decimal(str(b["o"])),
                    high=Decimal(str(b["h"])),
                    low=Decimal(str(b["l"])),
                    close=Decimal(str(b["c"])),
                    volume=int(b["v"]),
                )
                for b in bars_data
            ]

            # Cache the results
            self.cache.set(ticker, timeframe, bars)

            return bars

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch Alpaca data for {ticker}: {e}")
            return []

    def _is_cache_sufficient(self, cached: List[PriceBar], start_date: date, end_date: date) -> bool:
        first_date = cached[0].datetime.date() if cached else None
        last_date = cached[-1].datetime.date() if cached else None
        return first_date and last_date and first_date <= start_date and last_date >= end_date

    def _filter_by_date(self, bars: List[PriceBar], start_date: date, end_date: date) -> List[PriceBar]:
        return [b for b in bars if start_date <= b.datetime.date() <= end_date]


def get_price_provider(
    provider: str = "yfinance",
    cache_dir: str = "data/cache/prices",
    **kwargs
) -> Any:
    """
    Factory function to get a price provider.

    Args:
        provider: Provider name ("yfinance" or "alpaca")
        cache_dir: Cache directory path
        **kwargs: Additional provider-specific arguments

    Returns:
        Price provider instance
    """
    cache = PriceCache(cache_dir)

    if provider == "yfinance":
        return YFinanceProvider(cache)
    elif provider == "alpaca":
        return AlpacaPriceProvider(cache=cache, **kwargs)
    else:
        raise ValueError(f"Unknown provider: {provider}")
