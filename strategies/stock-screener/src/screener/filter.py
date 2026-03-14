"""Main stock filtering logic."""

import logging
from typing import Optional
from datetime import datetime

from ..providers.base import PriceData, FundamentalData, NewsHeadline
from .models import ScreenerConfig, FilterResult
from .criteria import CriteriaEvaluator
from ..scoring.ranker import StockRanker

logger = logging.getLogger(__name__)


class StockFilter:
    """Filters stocks based on criteria and ranks results."""

    def __init__(self, config: ScreenerConfig, ranker: StockRanker):
        self.config = config
        self.evaluator = CriteriaEvaluator(config.criteria)
        self.ranker = ranker

    def filter_stocks(
        self,
        price_data: dict[str, PriceData],
        fund_data: dict[str, FundamentalData],
        news_data: Optional[dict[str, list[NewsHeadline]]] = None
    ) -> list[FilterResult]:
        """
        Filter and rank stocks.

        Args:
            price_data: Mapping of symbol to price data
            fund_data: Mapping of symbol to fundamental data
            news_data: Optional mapping of symbol to news headlines

        Returns:
            List of filter results, sorted by rank
        """
        results = []
        symbols = set(price_data.keys()) | set(fund_data.keys())

        for symbol in symbols:
            price = price_data.get(symbol)
            fund = fund_data.get(symbol)
            news = news_data.get(symbol) if news_data else None

            passed, failures = self.evaluator.evaluate(symbol, price, fund)

            if passed:
                scores = self.ranker.calculate_scores(symbol, price, fund)
                rank_score = self.ranker.calculate_rank_score(scores)
            else:
                scores = {}
                rank_score = None

            result = FilterResult(
                symbol=symbol,
                passed=passed,
                scores=scores,
                failures=failures,
                rank_score=rank_score
            )
            results.append(result)

        # Sort by rank score descending
        passed_results = [r for r in results if r.passed]
        passed_results.sort(key=lambda x: x.rank_score or 0, reverse=True)

        # Apply max results limit
        max_results = self.config.output.get("max_results", 50)
        return passed_results[:max_results]
