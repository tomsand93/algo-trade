"""Stock ranking algorithms."""

import logging
from typing import Optional

from ..providers.base import PriceData, FundamentalData
from ..screener.models import StockScore

logger = logging.getLogger(__name__)


class StockRanker:
    """
    Ranks stocks based on value, quality, and momentum scores.

    Uses configurable weights to combine component scores into a final rank.
    """

    def __init__(self, weights: dict[str, float]):
        """
        Initialize ranker with scoring weights.

        Args:
            weights: Dict with value_score, quality_score, momentum_score weights
        """
        self.weights = weights
        self._validate_weights()

    def _validate_weights(self):
        """Ensure weights sum to 1.0."""
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            logger.warning(f"Weights sum to {total}, normalizing...")
            self.weights = {k: v / total for k, v in self.weights.items()}

    def calculate_scores(
        self,
        symbol: str,
        price_data: Optional[PriceData],
        fund_data: Optional[FundamentalData]
    ) -> dict[str, float]:
        """
        Calculate component scores for a stock.

        Returns dict with value_score, quality_score, momentum_score.
        """
        value = self._calculate_value_score(fund_data)
        quality = self._calculate_quality_score(fund_data)
        momentum = self._calculate_momentum_score(price_data, fund_data)

        return {
            "value_score": value,
            "quality_score": quality,
            "momentum_score": momentum,
        }

    def calculate_rank_score(self, scores: dict[str, float]) -> float:
        """Calculate final weighted rank score."""
        rank = (
            scores.get("value_score", 0) * self.weights.get("value_score", 0.4) +
            scores.get("quality_score", 0) * self.weights.get("quality_score", 0.3) +
            scores.get("momentum_score", 0) * self.weights.get("momentum_score", 0.3)
        )
        return round(rank, 3)

    # ============== Helper Functions ==============

    def _get_num(self, obj, *names) -> Optional[float]:
        """Get numeric value from object, trying multiple attribute names."""
        for name in names:
            v = getattr(obj, name, None)
            if v is None:
                continue
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            if v != v:  # NaN check
                continue
            return v
        return None

    def _clamp(self, x: float, lo: float = 0.0, hi: float = 100.0) -> float:
        """Clamp value to range [lo, hi]."""
        return max(lo, min(hi, float(x)))

    def _interp(self, x: Optional[float], points: list[tuple[float, float]]) -> float:
        """
        Piecewise-linear interpolation.
        points: list[(x_value, score)], sorted by x_value ascending.
        Clamps outside the range to endpoint scores.
        """
        if x is None:
            return 0.0
        x = float(x)
        if x <= points[0][0]:
            return float(points[0][1])
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            if x <= x2:
                if x2 == x1:
                    return float(y2)
                t = (x - x1) / (x2 - x1)
                return float(y1 + t * (y2 - y1))
        return float(points[-1][1])

    def _to_pct(self, v: Optional[float]) -> Optional[float]:
        """Convert decimal to percent if value appears to be decimal (abs <= 1.5)."""
        if v is None:
            return None
        return v * 100.0 if abs(v) <= 1.5 else v

    # ============== Scoring Functions ==============

    def _calculate_value_score(self, fund_data: Optional[FundamentalData]) -> float:
        """
        Value score (0-100).
        Based on P/E, P/B, and dividend yield - lower valuations score higher.
        Conservative rule: missing metrics contribute 0 (no renormalisation).

        Weights: 45% P/E, 35% P/B, 20% dividend yield.
        """
        if fund_data is None:
            return 0.0

        # Fetch metrics (ratios)
        pe = self._get_num(fund_data, "pe_ratio", "trailing_pe", "pe", "price_to_earnings", "price_earnings")
        pb = self._get_num(fund_data, "pb_ratio", "price_to_book", "pb", "price_book", "price_to_book_ratio")

        # Dividend yield may be decimal (0.034) or percent (3.4)
        div_yield = self._get_num(fund_data, "dividend_yield", "div_yield", "dividendYield", "dividend_yield_ttm")
        div_yield_pct = None
        if div_yield is not None:
            div_yield_pct = div_yield * 100.0 if abs(div_yield) <= 0.5 else div_yield
            if div_yield_pct < 0:
                div_yield_pct = 0.0

        # Map to 0-100 (broad, sector-agnostic defaults)
        # P/E: <10 excellent, >60 poor
        pe_score = 0.0
        if pe is not None and pe > 0:
            pe_score = self._interp(pe, [
                (10.0, 100.0),
                (15.0,  85.0),
                (25.0,  55.0),
                (40.0,  15.0),
                (60.0,   0.0),
            ])

        # P/B: <1 excellent, >10 poor
        pb_score = 0.0
        if pb is not None and pb > 0:
            pb_score = self._interp(pb, [
                (1.0, 100.0),
                (2.0,  85.0),
                (4.0,  55.0),
                (6.0,  15.0),
                (10.0,  0.0),
            ])

        # Dividend yield: >6% excellent, 0% poor
        div_score = self._interp(div_yield_pct, [
            (0.0,  0.0),
            (1.0, 25.0),
            (2.0, 45.0),
            (4.0, 80.0),
            (6.0, 100.0),
        ])

        # Weighted blend (missing => 0 contribution)
        score = (0.45 * pe_score) + (0.35 * pb_score) + (0.20 * div_score)
        return self._clamp(score)

    def _calculate_quality_score(self, fund_data: Optional[FundamentalData]) -> float:
        """
        Quality score (0-100).
        Uses ROE (profitability), D/E (balance-sheet risk), and growth proxy.
        Conservative rule: missing metrics contribute 0 (no renormalisation).

        Weights: 45% ROE, 35% D/E, 20% growth.
        """
        if fund_data is None:
            return 0.0

        # ROE: may be decimal (0.18) or percent (18.0)
        roe = self._get_num(fund_data, "roe", "return_on_equity", "returnOnEquity", "roe_ttm")
        roe_pct = self._to_pct(roe) if roe is not None else None

        # Leverage: D/E ratio (negative can occur with negative equity; treat as worst)
        de = self._get_num(fund_data, "debt_to_equity", "debt_equity", "de_ratio", "debtToEquity")
        de_score = 0.0
        if de is not None:
            if de < 0:
                de_score = 0.0
            else:
                de_score = self._interp(de, [
                    (0.0, 100.0),
                    (0.5,  90.0),
                    (1.0,  75.0),
                    (2.0,  40.0),
                    (3.0,  15.0),
                    (5.0,   0.0),
                ])

        # Growth proxies: may be decimal (0.12) or percent (12.0)
        rev_g = self._get_num(
            fund_data,
            "revenue_growth", "revenue_growth_3y", "revenue_cagr_3y", "sales_growth", "sales_growth_3y"
        )
        eps_g = self._get_num(
            fund_data,
            "eps_growth", "earnings_growth", "earnings_growth_3y", "net_income_growth", "income_growth"
        )

        rev_g_pct = self._to_pct(rev_g)
        eps_g_pct = self._to_pct(eps_g)

        rev_score = self._interp(rev_g_pct, [
            (0.0,  0.0),
            (5.0, 40.0),
            (10.0, 70.0),
            (15.0, 90.0),
            (25.0, 100.0),
        ])
        eps_score = self._interp(eps_g_pct, [
            (0.0,  0.0),
            (5.0, 40.0),
            (10.0, 70.0),
            (15.0, 90.0),
            (25.0, 100.0),
        ])

        growth_score = 0.5 * rev_score + 0.5 * eps_score

        # ROE: >30% excellent, 0% poor
        roe_score = self._interp(roe_pct, [
            (0.0,  0.0),
            (5.0, 25.0),
            (10.0, 55.0),
            (20.0, 85.0),
            (30.0, 100.0),
        ])

        score = (0.45 * roe_score) + (0.35 * de_score) + (0.20 * growth_score)
        return self._clamp(score)

    def _calculate_momentum_score(
        self,
        price_data: Optional[PriceData],
        fund_data: Optional[FundamentalData]
    ) -> float:
        """
        Momentum score (0-100).
        Combines: intermediate-horizon return, trend confirmation (MA), RSI health.
        Conservative rule: missing metrics contribute 0 (no renormalisation).

        Weights: 35% recent return, 35% MA trend, 30% RSI health.
        """
        if price_data is None:
            return 0.0

        # RSI (usually already 0-100)
        rsi = self._get_num(price_data, "rsi_14", "rsi14", "rsi", "relative_strength_index")
        rsi_score = self._interp(rsi, [
            (25.0,  0.0),
            (35.0, 25.0),
            (45.0, 55.0),
            (55.0, 85.0),
            (60.0, 100.0),
            (70.0,  80.0),
            (80.0,  40.0),
            (90.0,   0.0),
        ])

        # Trend: price vs moving averages
        price = self._get_num(price_data, "price", "close", "current_price")
        ma50 = self._get_num(price_data, "ma50", "sma_50", "ma_50", "moving_average_50", "sma50")
        ma200 = self._get_num(price_data, "ma200", "sma_200", "ma_200", "moving_average_200", "sma200")

        trend_score = 0.0
        if price is not None and ma200 is not None and ma200 > 0:
            trend_score += 50.0 if price > ma200 else 0.0
        if price is not None and ma50 is not None and ma50 > 0:
            trend_score += 25.0 if price > ma50 else 0.0
        if ma50 is not None and ma200 is not None and ma50 > 0 and ma200 > 0:
            trend_score += 25.0 if ma50 > ma200 else 0.0

        # Recent change proxy: use change_pct from price_data
        chg_pct = self._to_pct(self._get_num(price_data, "change_pct", "change", "pct_change"))

        return_score = self._interp(chg_pct, [
            (-30.0,  0.0),
            (-20.0, 10.0),
            (0.0,   40.0),
            (10.0,  60.0),
            (20.0,  80.0),
            (40.0, 100.0),
            (80.0, 100.0),
        ])

        score = (0.35 * return_score) + (0.35 * trend_score) + (0.30 * rsi_score)
        return self._clamp(score)
