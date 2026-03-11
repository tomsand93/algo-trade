"""OpenBB implementation for fundamental data."""

import logging
from typing import Optional
from datetime import datetime, timedelta

try:
    from openbb import obb
except ImportError:
    obb = None
    logging.warning("OpenBB not installed. Fundamental data will be limited.")

from .base import FundamentalProvider, FundamentalData

logger = logging.getLogger(__name__)


class OpenBBProvider(FundamentalProvider):
    """OpenBB fundamental data provider."""

    def __init__(self):
        if obb is None:
            raise ImportError("OpenBB is not installed. Run: pip install openbb")

    async def get_fundamentals(self, symbol: str) -> Optional[FundamentalData]:
        """Fetch fundamental data for a symbol."""
        try:
            # Get equity fundamentals
            result = obb.equity.fundamental.overview(symbol=symbol)

            if not result or not hasattr(result, 'results') or not result.results:
                # Fallback to basic data
                return self._get_basic_fundamentals(symbol)

            data = result.results[0] if isinstance(result.results, list) else result.results

            return FundamentalData(
                symbol=symbol,
                market_cap=data.get("marketCapitalization"),
                pe_ratio=data.get("peRatio"),
                pb_ratio=data.get("pbRatio"),
                dividend_yield=data.get("dividendYield"),
                revenue_growth=data.get("revenueGrowth"),
                eps_growth=data.get("earningsGrowth"),
                debt_to_equity=data.get("debtToEquity"),
                roe=data.get("returnOnEquity"),
                eps=data.get("eps")
            )

        except Exception as e:
            logger.warning(f"OpenBB error for {symbol}: {e}. Using fallback.")
            return self._get_basic_fundamentals(symbol)

    async def get_fundamentals_batch(self, symbols: list[str]) -> dict[str, FundamentalData]:
        """Fetch fundamentals for multiple symbols."""
        results = {}
        for symbol in symbols:
            data = await self.get_fundamentals(symbol)
            if data:
                results[symbol] = data
        return results

    def _get_basic_fundamentals(self, symbol: str) -> Optional[FundamentalData]:
        """Fallback to yfinance for basic fundamentals."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            info = ticker.info

            return FundamentalData(
                symbol=symbol,
                market_cap=info.get("marketCap"),
                pe_ratio=info.get("trailingPE"),
                pb_ratio=info.get("priceToBook"),
                dividend_yield=info.get("dividendYield"),
                revenue_growth=info.get("revenueGrowth"),  # May be None
                eps_growth=info.get("earningsGrowth"),
                debt_to_equity=info.get("debtToEquity"),
                roe=info.get("returnOnEquity"),
                eps=info.get("trailingEps")
            )
        except Exception as e:
            logger.error(f"Fallback fundamentals failed for {symbol}: {e}")
            return None
