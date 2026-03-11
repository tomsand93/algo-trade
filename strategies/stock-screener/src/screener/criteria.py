"""Criteria parsing and evaluation."""

import logging
from typing import Any, Optional

from ..providers.base import PriceData, FundamentalData
from .models import CriterionConfig, CriterionType, Operator

logger = logging.getLogger(__name__)


class CriteriaEvaluator:
    """Evaluates stocks against screening criteria."""

    def __init__(self, criteria: list[CriterionConfig]):
        self.criteria = criteria

    def evaluate(
        self,
        symbol: str,
        price_data: Optional[PriceData],
        fund_data: Optional[FundamentalData]
    ) -> tuple[bool, list[str]]:
        """
        Evaluate a stock against all criteria.

        Returns:
            (passed, failure_reasons)
        """
        failures = []

        for criterion in self.criteria:
            passed = self._evaluate_criterion(criterion, price_data, fund_data)
            if not passed:
                reason = self._format_failure(criterion)
                failures.append(reason)

        return len(failures) == 0, failures

    def _evaluate_criterion(
        self,
        criterion: CriterionConfig,
        price_data: Optional[PriceData],
        fund_data: Optional[FundamentalData]
    ) -> bool:
        """Evaluate a single criterion."""
        actual_value = self._get_metric_value(criterion, price_data, fund_data)

        if actual_value is None:
            # Missing data - fail the criterion
            return False

        return self._compare(actual_value, criterion.operator, criterion.value)

    def _get_metric_value(
        self,
        criterion: CriterionConfig,
        price_data: Optional[PriceData],
        fund_data: Optional[FundamentalData]
    ) -> Optional[float]:
        """Extract metric value from data objects."""
        metric = criterion.metric

        # Fundamental metrics
        if criterion.type == CriterionType.FUNDAMENTAL:
            if fund_data is None:
                return None

            metric_map = {
                "market_cap": getattr(fund_data, "market_cap", None),
                "pe_ratio": getattr(fund_data, "pe_ratio", None),
                "pb_ratio": getattr(fund_data, "pb_ratio", None),
                "dividend_yield": getattr(fund_data, "dividend_yield", None),
                "revenue_growth": getattr(fund_data, "revenue_growth", None),
                "eps_growth": getattr(fund_data, "eps_growth", None),
                "debt_to_equity": getattr(fund_data, "debt_to_equity", None),
                "roe": getattr(fund_data, "roe", None),
                "eps": getattr(fund_data, "eps", None),
            }
            return metric_map.get(metric)

        # Technical metrics
        elif criterion.type == CriterionType.TECHNICAL:
            if price_data is None:
                return None

            # Special handling for boolean-like metrics
            if metric == "price_above_ma50":
                return 1.0 if (price_data.ma50 and price_data.price > price_data.ma50) else 0.0
            if metric == "price_above_ma200":
                return 1.0 if (price_data.ma200 and price_data.price > price_data.ma200) else 0.0

            metric_map = {
                "rsi_14": getattr(price_data, "rsi_14", None),
                "price": getattr(price_data, "price", None),
                "volume": getattr(price_data, "volume", None),
            }
            return metric_map.get(metric)

        return None

    def _compare(self, actual: float, op: Operator, expected: float) -> bool:
        """Compare actual vs expected value."""
        if op == Operator.GT:
            return actual > expected
        elif op == Operator.GTE:
            return actual >= expected
        elif op == Operator.LT:
            return actual < expected
        elif op == Operator.LTE:
            return actual <= expected
        elif op == Operator.EQ:
            return abs(actual - expected) < 1e-6
        elif op == Operator.NE:
            return abs(actual - expected) >= 1e-6
        return False

    def _format_failure(self, criterion: CriterionConfig) -> str:
        """Format a failure message."""
        return f"{criterion.metric} {criterion.operator.value} {criterion.value}"
