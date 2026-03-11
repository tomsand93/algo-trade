"""Financial Modeling Prep provider for historical fundamentals."""

import logging
import requests
from typing import Optional
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
    import os
    API_KEY = os.getenv("FMP_API_KEY")
except ImportError:
    API_KEY = None

from .base import FundamentalProvider, FundamentalData

logger = logging.getLogger(__name__)


class FMPProvider(FundamentalProvider):
    """
    Financial Modeling Prep fundamentals provider.

    Provides historical point-in-time fundamentals for backtesting.
    """

    BASE_URL = "https://financialmodelingprep.com/api/v3"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or API_KEY
        if not self.api_key:
            raise ValueError("FMP_API_KEY required. Get free key at https://site.financialmodelingprep.com/")

    async def get_fundamentals(self, symbol: str, date: str = None) -> Optional[FundamentalData]:
        """
        Fetch fundamentals for a symbol at a specific date.

        Args:
            symbol: Stock ticker
            date: Optional date (YYYY-MM-DD) for historical point-in-time data
        """
        try:
            # Get TTM ratios (current or historical)
            if date:
                url = f"{self.BASE_URL}/ratios-ttm/{symbol}?date={date}&apikey={self.api_key}"
            else:
                url = f"{self.BASE_URL}/ratios-ttm/{symbol}?apikey={self.api_key}"

            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data or isinstance(data, str):
                return self._get_profile_fundamentals(symbol)

            # FMP returns array; take most recent
            if isinstance(data, list):
                if not data:
                    return None
                ratios = data[0]
            else:
                ratios = data

            return FundamentalData(
                symbol=symbol,
                market_cap=ratios.get("marketCapTTM"),
                pe_ratio=ratios.get("peRatioTTM"),
                pb_ratio=ratios.get("pbRatioTTM"),
                dividend_yield=ratios.get("dividendYieldTTM"),  # Already as decimal
                revenue_growth=ratios.get("revenueGrowthTTM") / 100 if ratios.get("revenueGrowthTTM") else None,
                eps_growth=ratios.get("epsGrowthTTM") / 100 if ratios.get("epsGrowthTTM") else None,
                debt_to_equity=ratios.get("debtEquityRatioTTM"),
                roe=ratios.get("roeTTM") / 100 if ratios.get("roeTTM") else None,
                eps=ratios.get("epsTTM")
            )

        except Exception as e:
            logger.error(f"FMP error for {symbol}: {e}")
            return None

    async def get_fundamentals_batch(self, symbols: list[str], date: str = None) -> dict[str, FundamentalData]:
        """Fetch fundamentals for multiple symbols."""
        results = {}
        for symbol in symbols:
            data = await self.get_fundamentals(symbol, date)
            if data:
                results[symbol] = data
        return results

    def get_historical_ratios(self, symbol: str, years: int = 10) -> list[dict]:
        """
        Fetch historical ratios for backtesting.

        Args:
            symbol: Stock ticker
            years: How many years of history to fetch

        Returns:
            List of historical ratio records with dates
        """
        try:
            url = f"{self.BASE_URL}/ratios-ttm/{symbol}?apikey={self.api_key}&limit={years * 4}"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list):
                # Return with date field for each record
                return [{
                    "date": r.get("date"),
                    "pe_ratio": r.get("peRatioTTM"),
                    "pb_ratio": r.get("pbRatioTTM"),
                    "dividend_yield": r.get("dividendYieldTTM"),
                    "roe": r.get("roeTTM"),
                    "revenue_growth": r.get("revenueGrowthTTM"),
                    "market_cap": r.get("marketCapTTM"),
                } for r in data if r.get("date")]

            return []

        except Exception as e:
            logger.error(f"Error fetching historical ratios for {symbol}: {e}")
            return []

    def _get_profile_fundamentals(self, symbol: str) -> Optional[FundamentalData]:
        """Fallback to profile endpoint for basic data."""
        try:
            url = f"{self.BASE_URL}/profile/{symbol}?apikey={self.api_key}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data or isinstance(data, str):
                return None

            profile = data[0] if isinstance(data, list) else data

            return FundamentalData(
                symbol=symbol,
                market_cap=profile.get("mktCap"),
                pe_ratio=profile.get("pe"),
                pb_ratio=None,  # Not in profile
                dividend_yield=profile.get("lastDiv"),
                revenue_growth=None,
                eps_growth=None,
                debt_to_equity=None,
                roe=None,
                eps=profile.get("eps")
            )

        except Exception as e:
            logger.error(f"FMP profile error for {symbol}: {e}")
            return None


# Helper function for backtesting
def get_point_in_time_fundamentals(symbol: str, date: str) -> Optional[FundamentalData]:
    """
    Get fundamentals as they appeared on a specific date.

    Args:
        symbol: Stock ticker
        date: Date in YYYY-MM-DD format

    Returns:
        FundamentalData with point-in-time values
    """
    provider = FMPProvider()
    import asyncio
    return asyncio.run(provider.get_fundamentals(symbol, date))
