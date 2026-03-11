"""
Proven Factors Ranker - Based on quantitative research evidence.

Factors supported by academic and industry research:
- Strong factors: ROIC/ROE, FCF margin, Momentum (6-12M), Earnings revisions
- Valuation: EV/EBITDA, P/FCF (relative to history/peers)
- Conditional: Growth, Low volatility, Leverage

Three weighting schemes:
- Option A: Equal weights (25% each across 4 factors)
- Option B: Quality first (40% quality, 25% value, 20% momentum, 15% revisions)
- Option C: Trend focused (40% momentum, 25% revisions, 20% quality, 15% value)
"""

import logging
from typing import Optional, Dict, Literal
from dataclasses import dataclass
from enum import Enum

from ..providers.base import PriceData, FundamentalData

logger = logging.getLogger(__name__)


class WeightingScheme(Enum):
    """Weighting scheme options."""
    EQUAL = "equal"              # 25% each across 4 factors
    QUALITY_FIRST = "quality"    # 40% quality, 25% value, 20% momentum, 15% revisions
    TREND_FOCUSED = "trend"      # 40% momentum, 25% revisions, 20% quality, 15% value


@dataclass
class FactorScores:
    """Individual factor scores (0-100)."""
    profitability: float = 50.0      # ROIC/ROE + margins
    free_cash_flow: float = 50.0     # FCF margin
    valuation: float = 50.0          # EV/EBITDA, P/FCF vs history
    momentum_6m: float = 50.0        # 6-month return
    momentum_12m: float = 50.0       # 12-month return
    earnings_revisions: float = 50.0 # Analyst estimate changes (if available)
    earnings_surprise: float = 50.0  # Recent beat/miss
    growth: float = 50.0             # Revenue/EPS growth
    low_volatility: float = 50.0     # Inverse of vol
    leverage: float = 50.0           # Inverse of debt/equity

    def get_quality_score(self) -> float:
        """Combined quality score (profitability + FCF)."""
        return (self.profitability + self.free_cash_flow) / 2

    def get_momentum_score(self) -> float:
        """Combined momentum score (6M + 12M)."""
        return (self.momentum_6m + self.momentum_12m) / 2

    def get_revisions_score(self) -> float:
        """Combined revisions score (revisions + surprise)."""
        return (self.earnings_revisions + self.earnings_surprise) / 2


class ProvenFactorsRanker:
    """
    Ranker using factors proven by quantitative research.

    References:
    - "Quantitative Value" by Gray & Carlisle (ROIC, EV/EBITDA)
    - "Expected Returns" by Antti Ilmanen (momentum, value, quality)
    - AQR research on quality (profitability, earnings quality)
    - Research on earnings momentum (revisions, surprises)
    """

    # Weight configurations for each scheme
    WEIGHTS = {
        WeightingScheme.EQUAL: {
            "quality": 0.25,      # Profitability + FCF
            "value": 0.25,        # Valuation vs history
            "momentum": 0.25,     # 6-12M returns
            "revisions": 0.25,    # Earnings revisions
        },
        WeightingScheme.QUALITY_FIRST: {
            "quality": 0.40,
            "value": 0.25,
            "momentum": 0.20,
            "revisions": 0.15,
        },
        WeightingScheme.TREND_FOCUSED: {
            "momentum": 0.40,
            "revisions": 0.25,
            "quality": 0.20,
            "value": 0.15,
        },
    }

    def __init__(self, scheme: WeightingScheme = WeightingScheme.EQUAL):
        """
        Initialize ranker with weighting scheme.

        Args:
            scheme: Weighting scheme to use
        """
        self.scheme = scheme
        self.weights = self.WEIGHTS[scheme]
        logger.info(f"ProvenFactorsRanker initialized with {scheme.value} scheme")

    def calculate_scores(
        self,
        symbol: str,
        price_data: Optional[PriceData],
        fund_data: Optional[FundamentalData],
        hist_data: Optional[Dict] = None
    ) -> Dict[str, float]:
        """
        Calculate all factor scores.

        Args:
            symbol: Stock symbol
            price_data: Current price data
            fund_data: Fundamental data
            hist_data: Historical data dict with:
                - returns_1m, 3m, 6m, 12m
                - volatility_21d, 63d, 252d
                - historical_valuations (for relative comparison)

        Returns:
            dict with score and component scores
        """
        if price_data is None:
            return {"score": 0.0, "factors": FactorScores()}

        factors = FactorScores()

        # ===== PROFITABILITY / QUALITY =====
        factors.profitability = self._score_profitability(fund_data)
        factors.free_cash_flow = self._score_fcf(fund_data)

        # ===== VALUATION (relative) =====
        factors.valuation = self._score_valuation_relative(fund_data, hist_data)

        # ===== MOMENTUM =====
        if hist_data:
            factors.momentum_6m = self._score_return(hist_data.get("return_126d", 0), 126)
            factors.momentum_12m = self._score_return(hist_data.get("return_252d", 0), 252)
        else:
            # Fallback to price data
            factors.momentum_6m = 50.0
            factors.momentum_12m = 50.0

        # ===== EARNINGS REVISIONS =====
        if hist_data:
            factors.earnings_revisions = self._score_revisions(hist_data.get("estimate_revision", 0))
            factors.earnings_surprise = self._score_surprise(hist_data.get("last_surprise_pct", 0))
        else:
            factors.earnings_revisions = 50.0
            factors.earnings_surprise = 50.0

        # ===== CONDITIONAL FACTORS =====
        if fund_data:
            factors.growth = self._score_growth(fund_data)
        if hist_data:
            factors.low_volatility = self._score_low_vol(hist_data.get("volatility_252d", 0))
        if fund_data:
            factors.leverage = self._score_low_leverage(fund_data)

        # Calculate composite scores
        quality_score = factors.get_quality_score()
        momentum_score = factors.get_momentum_score()
        revisions_score = factors.get_revisions_score()

        # Weighted combination
        score = (
            quality_score * self.weights["quality"] +
            factors.valuation * self.weights["value"] +
            momentum_score * self.weights["momentum"] +
            revisions_score * self.weights["revisions"]
        )

        return {
            "score": round(score, 2),
            "factors": factors,
            "components": {
                "quality": round(quality_score, 2),
                "value": round(factors.valuation, 2),
                "momentum": round(momentum_score, 2),
                "revisions": round(revisions_score, 2),
            },
            "weights": self.weights,
        }

    # ===== SCORING FUNCTIONS =====

    def _score_profitability(self, fund_data: Optional[FundamentalData]) -> float:
        """
        Score profitability based on ROIC/ROE and margins.

        High ROIC (>15%) and high operating margins (>20%) are best.
        """
        if fund_data is None:
            return 50.0

        score = 50.0

        # ROE / ROIC
        roe = getattr(fund_data, "roe", None) or getattr(fund_data, "roic", None)
        if roe is not None:
            roe_pct = roe * 100 if abs(roe) <= 1 else roe
            if roe_pct > 20:
                score += 25
            elif roe_pct > 15:
                score += 20
            elif roe_pct > 10:
                score += 10
            elif roe_pct < 5:
                score -= 15
            elif roe_pct < 0:
                score -= 30

        # Operating margin
        op_margin = getattr(fund_data, "operating_margin", None) or getattr(fund_data, "profit_margin", None)
        if op_margin is not None:
            op_margin_pct = op_margin * 100 if abs(op_margin) <= 1 else op_margin
            if op_margin_pct > 25:
                score += 15
            elif op_margin_pct > 20:
                score += 10
            elif op_margin_pct > 15:
                score += 5
            elif op_margin_pct < 5:
                score -= 10
            elif op_margin_pct < 0:
                score -= 20

        return max(0, min(100, score))

    def _score_fcf(self, fund_data: Optional[FundamentalData]) -> float:
        """
        Score free cash flow generation.

        FCF margin > 10% is excellent, 5-10% is good, < 0% is bad.
        """
        if fund_data is None:
            return 50.0

        # FCF margin is often not directly available
        # Use profit margin and low debt as proxy
        profit_margin = getattr(fund_data, "profit_margin", None)
        debt_to_equity = getattr(fund_data, "debt_to_equity", None)

        score = 50.0

        if profit_margin is not None:
            margin_pct = profit_margin * 100 if abs(profit_margin) <= 1 else profit_margin
            if margin_pct > 15:
                score += 25
            elif margin_pct > 10:
                score += 20
            elif margin_pct > 5:
                score += 10
            elif margin_pct < 0:
                score -= 20

        # Low debt = more FCF flexibility
        if debt_to_equity is not None and debt_to_equity < 1.0:
            score += 10

        return max(0, min(100, score))

    def _score_valuation_relative(
        self,
        fund_data: Optional[FundamentalData],
        hist_data: Optional[Dict] = None
    ) -> float:
        """
        Score valuation relative to history/peers.

        Uses P/E, EV/EBITDA, P/FCF.
        Lower is better, but need context.
        """
        if fund_data is None:
            return 50.0

        score = 50.0

        # P/E ratio (check vs historical range if available)
        pe = getattr(fund_data, "pe_ratio", None)
        if pe is not None:
            if pe < 15:
                score += 20
            elif pe < 20:
                score += 10
            elif pe > 40:
                score -= 20
            elif pe > 60:
                score -= 30

        # EV/EBITDA
        ev_ebitda = getattr(fund_data, "ev_ebitda", None)
        if ev_ebitda is not None:
            if ev_ebitda < 10:
                score += 15
            elif ev_ebitda < 15:
                score += 10
            elif ev_ebitda > 25:
                score -= 15
            elif ev_ebitda > 40:
                score -= 25

        # P/B ratio
        pb = getattr(fund_data, "pb_ratio", None)
        if pb is not None:
            if pb < 1.5:
                score += 10
            elif pb < 3:
                score += 5
            elif pb > 8:
                score -= 15

        return max(0, min(100, score))

    def _score_return(self, return_pct: float, days: int) -> float:
        """Score return over period (momentum factor)."""
        # Normalize expected return by period length
        if days <= 63:
            # 3-month: +40% = 100, -20% = 0
            return max(0, min(100, (return_pct + 20) / 60 * 100))
        elif days <= 126:
            # 6-month: +60% = 100, -30% = 0
            return max(0, min(100, (return_pct + 30) / 90 * 100))
        else:
            # 12-month: +100% = 100, -40% = 0
            return max(0, min(100, (return_pct + 40) / 140 * 100))

    def _score_revisions(self, revision_pct: float) -> float:
        """
        Score analyst estimate revisions.

        Positive revisions (analysts raising estimates) are bullish.
        """
        if revision_pct > 5:
            return 100
        elif revision_pct > 2:
            return 80
        elif revision_pct > 0:
            return 60
        elif revision_pct > -2:
            return 40
        elif revision_pct > -5:
            return 20
        else:
            return 0

    def _score_surprise(self, surprise_pct: float) -> float:
        """
        Score earnings surprise.

        Positive surprise (beating estimates) is bullish.
        """
        if surprise_pct > 10:
            return 100
        elif surprise_pct > 5:
            return 85
        elif surprise_pct > 0:
            return 65
        elif surprise_pct > -5:
            return 35
        elif surprise_pct > -10:
            return 20
        else:
            return 0

    def _score_growth(self, fund_data: FundamentalData) -> float:
        """Score growth (revenue/EPS)."""
        score = 50.0

        rev_growth = getattr(fund_data, "revenue_growth", None)
        if rev_growth is not None:
            growth_pct = rev_growth * 100 if abs(rev_growth) <= 1 else rev_growth
            if growth_pct > 20:
                score += 25
            elif growth_pct > 15:
                score += 20
            elif growth_pct > 10:
                score += 15
            elif growth_pct > 5:
                score += 10
            elif growth_pct < 0:
                score -= 20

        return max(0, min(100, score))

    def _score_low_vol(self, vol: float) -> float:
        """
        Score low volatility.

        Lower volatility = higher score (inverse relationship).
        """
        if vol < 1.5:
            return 100
        elif vol < 2.0:
            return 80
        elif vol < 2.5:
            return 60
        elif vol < 3.5:
            return 40
        else:
            return 20

    def _score_low_leverage(self, fund_data: FundamentalData) -> float:
        """
        Score low leverage (inverse of debt/equity).

        Lower debt = higher score.
        """
        de = getattr(fund_data, "debt_to_equity", None)
        if de is None:
            return 50.0

        if de < 0.3:
            return 100
        elif de < 0.5:
            return 85
        elif de < 1.0:
            return 70
        elif de < 2.0:
            return 40
        elif de < 3.0:
            return 20
        else:
            return 0
