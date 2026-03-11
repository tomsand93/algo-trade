"""yfinance implementation for price and technical data."""

import yfinance as yf
import logging
from typing import Optional
from datetime import datetime, timedelta

from .base import PriceProvider, PriceData

logger = logging.getLogger(__name__)


class YFinanceProvider(PriceProvider):
    """yfinance price data provider."""

    def __init__(self, cache_ttl_seconds: int = 300):
        self._cache = {}
        self._cache_ttl = cache_ttl_seconds

    async def get_price(self, symbol: str) -> Optional[PriceData]:
        """Fetch current price and technicals for a symbol."""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            # Need at least 200 days for MA200
            history = ticker.history(period="1y", interval="1d")

            if info is None or history.empty:
                logger.warning(f"No data for {symbol}")
                return None

            # Current price info
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            prev_close = info.get("previousClose")
            change = price - prev_close if prev_close else 0
            change_pct = (change / prev_close * 100) if prev_close else 0

            # Technical indicators
            rsi_14 = self._calculate_rsi(history, 14)
            ma50 = self._calculate_ma(history, 50)
            ma200 = self._calculate_ma(history, 200)
            atr = self._calculate_atr(history, 14)

            return PriceData(
                symbol=symbol,
                price=price,
                change=change,
                change_pct=change_pct,
                volume=info.get("volume"),
                rsi_14=rsi_14,
                ma50=ma50,
                ma200=ma200,
                atr=atr
            )

        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            return None

    async def get_prices_batch(self, symbols: list[str]) -> dict[str, PriceData]:
        """Fetch prices for multiple symbols."""
        results = {}
        for symbol in symbols:
            data = await self.get_price(symbol)
            if data:
                results[symbol] = data
        return results

    def _calculate_rsi(self, history, period: int = 14) -> Optional[float]:
        """Calculate RSI indicator."""
        try:
            closes = history["Close"].values
            if len(closes) < period + 1:
                return None

            deltas = closes[1:] - closes[:-1]
            gains = deltas.copy()
            losses = deltas.copy()
            gains[gains < 0] = 0
            losses[losses > 0] = 0
            losses = -losses

            avg_gain = gains[:period].mean()
            avg_loss = losses[:period].mean()

            for i in range(period, len(gains)):
                avg_gain = (avg_gain * (period - 1) + gains[i]) / period
                avg_loss = (avg_loss * (period - 1) + losses[i]) / period

            if avg_loss == 0:
                return 100.0

            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            return round(rsi, 2)

        except Exception:
            return None

    def _calculate_ma(self, history, period: int) -> Optional[float]:
        """Calculate Simple Moving Average."""
        try:
            if len(history) < period:
                return None
            return round(history["Close"].tail(period).mean(), 2)
        except Exception:
            return None

    def _calculate_atr(self, history, period: int = 14) -> Optional[float]:
        """Calculate Average True Range."""
        try:
            if len(history) < period + 1:
                return None

            high = history["High"].values
            low = history["Low"].values
            close = history["Close"].values

            tr_list = []
            for i in range(1, len(history)):
                hl = high[i] - low[i]
                hc = abs(high[i] - close[i-1])
                lc = abs(low[i] - close[i-1])
                tr_list.append(max(hl, hc, lc))

            atr = sum(tr_list[-period:]) / period
            return round(atr, 2)

        except Exception:
            return None
