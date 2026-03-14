"""Correlation-weighted scoring based on empirical backtesting results.

Weights are assigned proportionally to each metric's correlation with forward returns,
derived from analyzing 3,935 observations across 147 stocks (2019-2026).
"""

import logging
from typing import Optional
import numpy as np

from ..providers.base import PriceData, FundamentalData

logger = logging.getLogger(__name__)


# Correlation values from backtesting (90-day forward returns)
CORRELATIONS = {
    # Momentum: Volatility (strongest predictors)
    "volatility_63d": 0.1497,
    "volatility_21d": 0.1070,

    # Momentum: Trend
    "market_cap": 0.1174,
    "ma50_slope": 0.1071,
    "pct_above_ma200": 0.0708,
    "pct_above_ma50": 0.0588,

    # Momentum: Returns
    "return_63d": 0.0758,
    "return_126d": 0.0660,
    "return_252d": 0.0636,
    "return_21d": 0.0614,

    # Growth (caveat: current data only)
    "revenue_growth": 0.0803,
    "pe_ratio": 0.1141,  # Note: positive means growth beats value

    # Quality (caveat: current data only)
    "profit_margin": 0.0525,

    # Negative correlations (inverse relationship)
    "dividend_yield": -0.1327,  # High yield = low returns
}


class CorrelationWeightedRanker:
    """
    Scoring ranker with weights based on empirical correlation analysis.

    Only uses metrics that showed statistically significant positive correlation
    with 90-day forward returns in backtesting (2019-2026, 147 stocks, 3,935 obs).
    """

    def __init__(self, normalize: bool = True):
        """
        Initialize ranker with correlation-based weights.

        Args:
            normalize: If True, normalize weights to sum to 1.0
        """
        self.normalize = normalize

        # Group metrics by category for clarity
        self.weight_groups = {
            "volatility": ["volatility_63d", "volatility_21d"],
            "trend": ["market_cap", "ma50_slope", "pct_above_ma200", "pct_above_ma50"],
            "momentum_returns": ["return_63d", "return_126d", "return_252d", "return_21d"],
            "growth": ["revenue_growth", "pe_ratio"],  # P/E positive = growth preference
            "quality": ["profit_margin"],
        }

        # Calculate total positive correlation for normalization
        positive_corr_sum = sum(max(0, c) for c in CORRELATIONS.values())

        # Calculate weights (proportional to correlation strength)
        self.weights = {}
        for metric, corr in CORRELATIONS.items():
            if corr > 0:
                # Weight proportional to correlation
                self.weights[metric] = corr / positive_corr_sum if normalize else corr
            else:
                # Negative correlation metrics are handled separately (inverse scoring)
                self.weights[metric] = abs(corr) / positive_corr_sum if normalize else abs(corr)

        logger.info(f"CorrelationWeightedRanker initialized with {len(self.weights)} metrics")
        logger.info(f"Total positive correlation weight: {sum(w for m, w in self.weights.items() if CORRELATIONS[m] > 0):.3f}")

    def calculate_score(
        self,
        symbol: str,
        price_data: Optional[PriceData],
        fund_data: Optional[FundamentalData],
        hist_data: Optional[dict] = None
    ) -> dict[str, float]:
        """
        Calculate correlation-weighted score for a stock.

        Args:
            symbol: Stock symbol
            price_data: Current price data (required)
            fund_data: Fundamental data (optional, for growth/quality metrics)
            hist_data: Historical price data dict with returns and volatility
                       If None, will compute from price_data where possible

        Returns:
            dict with score, component_scores, and breakdown
        """
        if price_data is None:
            return {"score": 0.0, "component_scores": {}, "breakdown": {}}

        component_scores = {}
        raw_scores = {}

        # ===== VOLATILITY METRICS =====
        # Note: We need historical data for proper volatility calculation
        if hist_data:
            vol_63d = hist_data.get("volatility_63d", 0)
            vol_21d = hist_data.get("volatility_21d", 0)

            # Normalize volatility: higher is better (0-100 scale)
            # Use 90th percentile as max (~4% daily vol)
            raw_scores["volatility_63d"] = self._normalize_volatility(vol_63d)
            raw_scores["volatility_21d"] = self._normalize_volatility(vol_21d)
        else:
            # Fallback: can't compute without history
            raw_scores["volatility_63d"] = 50.0
            raw_scores["volatility_21d"] = 50.0

        # ===== TREND METRICS =====
        # Market cap: normalize log-scale (larger is better)
        if fund_data and fund_data.market_cap:
            log_mcap = np.log10(fund_data.market_cap)
            # Scale: $1B = 0, $1T = 100
            raw_scores["market_cap"] = self._clamp((log_mcap - 9) / 3 * 100)
        else:
            raw_scores["market_cap"] = 50.0

        # MA slope: need historical data
        if hist_data and "ma50_slope" in hist_data:
            raw_scores["ma50_slope"] = self._normalize_ma_slope(hist_data["ma50_slope"])
        else:
            raw_scores["ma50_slope"] = 50.0

        # Price vs MA
        if price_data.ma200 and price_data.price:
            pct_above_ma200 = ((price_data.price - price_data.ma200) / price_data.ma200) * 100
            raw_scores["pct_above_ma200"] = self._normalize_pct_above(pct_above_ma200)
        else:
            raw_scores["pct_above_ma200"] = 50.0

        if price_data.ma50 and price_data.price:
            pct_above_ma50 = ((price_data.price - price_data.ma50) / price_data.ma50) * 100
            raw_scores["pct_above_ma50"] = self._normalize_pct_above(pct_above_ma50)
        else:
            raw_scores["pct_above_ma50"] = 50.0

        # ===== MOMENTUM RETURNS =====
        if hist_data:
            raw_scores["return_63d"] = self._normalize_return(hist_data.get("return_63d", 0), 63)
            raw_scores["return_126d"] = self._normalize_return(hist_data.get("return_126d", 0), 126)
            raw_scores["return_252d"] = self._normalize_return(hist_data.get("return_252d", 0), 252)
            raw_scores["return_21d"] = self._normalize_return(hist_data.get("return_21d", 0), 21)
        else:
            raw_scores["return_63d"] = 50.0
            raw_scores["return_126d"] = 50.0
            raw_scores["return_252d"] = 50.0
            raw_scores["return_21d"] = 50.0

        # ===== GROWTH METRICS =====
        if fund_data:
            # Revenue growth: higher is better
            rev_growth = fund_data.revenue_growth or 0
            raw_scores["revenue_growth"] = self._normalize_growth(rev_growth)

            # P/E ratio: HIGHER is better (growth beats value in our test period)
            pe = fund_data.pe_ratio
            if pe:
                # Scale: P/E 10 = 0, P/E 50+ = 100
                raw_scores["pe_ratio"] = self._clamp((pe - 10) / 40 * 100)
            else:
                raw_scores["pe_ratio"] = 50.0
        else:
            raw_scores["revenue_growth"] = 50.0
            raw_scores["pe_ratio"] = 50.0

        # ===== QUALITY METRICS =====
        if fund_data:
            margin = fund_data.profit_margin if hasattr(fund_data, 'profit_margin') else None
            if margin is None:
                # Try ROE as proxy
                margin = fund_data.roe
            if margin:
                # Normalize margin: 0% = 0, 30%+ = 100
                raw_scores["profit_margin"] = self._clamp(margin / 30 * 100)
            else:
                raw_scores["profit_margin"] = 50.0
        else:
            raw_scores["profit_margin"] = 50.0

        # ===== DIVIDEND YIELD (INVERSE) =====
        # High dividend yield = negative correlation = inverse score
        if fund_data and fund_data.dividend_yield:
            div_yield = fund_data.dividend_yield
            # Invert: 0% yield = 100 score, 5%+ yield = 0 score
            raw_scores["dividend_yield"] = self._clamp(100 - div_yield / 5 * 100)
        else:
            raw_scores["dividend_yield"] = 50.0

        # Calculate weighted score
        score = 0.0
        for metric, weight in self.weights.items():
            if metric in raw_scores:
                corr = CORRELATIONS[metric]
                if corr > 0:
                    score += raw_scores[metric] * weight
                else:
                    # Negative correlation: already inverted in raw score
                    score += raw_scores[metric] * weight

        score = self._clamp(score)

        return {
            "score": round(score, 2),
            "component_scores": raw_scores,
            "weights": self.weights,
        }

    def _clamp(self, x: float, lo: float = 0.0, hi: float = 100.0) -> float:
        return max(lo, min(hi, float(x)))

    def _normalize_volatility(self, vol: float) -> float:
        """Normalize daily volatility to 0-100 scale."""
        # 1% vol = 25, 4% vol = 100
        return self._clamp(vol / 4 * 100)

    def _normalize_ma_slope(self, slope: float) -> float:
        """Normalize MA slope (percent over period) to 0-100."""
        # +10% slope = 100, -5% slope = 0
        return self._clamp((slope + 5) / 15 * 100)

    def _normalize_pct_above(self, pct: float) -> float:
        """Normalize percent above MA to 0-100."""
        # +50% above = 100, -20% below = 0
        return self._clamp((pct + 20) / 70 * 100)

    def _normalize_return(self, ret: float, days: int) -> float:
        """Normalize return to 0-100 based on period."""
        # Scale expected return by period length
        if days <= 21:
            # 1-month: +20% = 100, -15% = 0
            return self._clamp((ret + 15) / 35 * 100)
        elif days <= 63:
            # 3-month: +40% = 100, -20% = 0
            return self._clamp((ret + 20) / 60 * 100)
        else:
            # 6-month+: +80% = 100, -30% = 0
            return self._clamp((ret + 30) / 110 * 100)

    def _normalize_growth(self, growth: float) -> float:
        """Normalize growth rate to 0-100."""
        # 30% growth = 100, -10% = 0
        return self._clamp((growth + 10) / 40 * 100)
