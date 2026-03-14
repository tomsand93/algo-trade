"""Finnhub news provider with sentiment analysis."""

import os
import logging
from typing import Optional
from datetime import datetime, timedelta

try:
    import finnhub
except ImportError:
    finnhub = None

from .base import NewsProvider, NewsHeadline

logger = logging.getLogger(__name__)


class FinnhubNewsProvider(NewsProvider):
    """Finnhub news provider with basic sentiment."""

    def __init__(self, api_key: Optional[str] = None):
        if finnhub is None:
            raise ImportError("finnhub-python not installed. Run: pip install finnhub-python")

        self.api_key = api_key or os.getenv("FINNHUB_API_KEY")
        if not self.api_key:
            raise ValueError("FINNHUB_API_KEY required. Set in .env or pass to constructor.")

        self.client = finnhub.Client(api_key=self.api_key)

    async def get_news(self, symbol: str, days_back: int = 7, limit: int = 5) -> list[NewsHeadline]:
        """Fetch recent news for a symbol."""
        try:
            to_date = datetime.now()
            from_date = to_date - timedelta(days=days_back)

            news_data = self.client.company_news(
                symbol,
                _from=from_date.strftime("%Y-%m-%d"),
                to=to_date.strftime("%Y-%m-%d")
            )

            headlines = []
            for item in news_data[:limit]:
                headlines.append(NewsHeadline(
                    title=item.get("headline", ""),
                    source=item.get("source", ""),
                    url=item.get("url", ""),
                    published_at=datetime.fromtimestamp(item.get("datetime", 0)).isoformat(),
                    sentiment=self._analyze_sentiment(item.get("headline", ""))
                ))

            return headlines

        except Exception as e:
            logger.error(f"Error fetching news for {symbol}: {e}")
            return []

    def _analyze_sentiment(self, text: str) -> Optional[float]:
        """Basic sentiment analysis using keyword matching."""
        if not text:
            return None

        positive_words = [
            "beat", "exceed", "growth", "gain", "rise", "surge", "rally",
            "strong", "upgrade", "buy", "outperform", "bullish", "profit",
            "record", "high", "breakthrough", "expansion", "dividend"
        ]

        negative_words = [
            "miss", "fall", "drop", "decline", "loss", "cut", "downgrade",
            "sell", "underperform", "bearish", "weak", "concern", "risk",
            "layoff", "investigation", "lawsuit", "recall", "lower"
        ]

        text_lower = text.lower()
        score = 0

        for word in positive_words:
            if word in text_lower:
                score += 0.2

        for word in negative_words:
            if word in text_lower:
                score -= 0.2

        return max(-1.0, min(1.0, score)) if score != 0 else 0.0
