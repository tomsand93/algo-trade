"""
Candlestick Pro - Dynamic Timeframe Selection

Analyzes multiple timeframes and selects the optimal one for pattern detection.
"""
from typing import List, Dict, Tuple
import math
from src.models import Candle, TimeFrameAnalysis, TimeFrameStyle
from src.indicators import (
    compute_atr, detect_trend, calculate_noise_score
)

EPSILON = 1e-10


class TimeframeSelector:
    """
    Dynamically selects the best timeframe for pattern detection.

    Selection criteria:
    1. Clean structure (low noise)
    2. Clear trend or range (not chop)
    3. Appropriate volatility (neither dead nor chaotic)
    4. Sufficient data history
    """

    def __init__(
        self,
        preferred_style: TimeFrameStyle = TimeFrameStyle.INTRADAY,
        min_candles: int = 100
    ):
        self.preferred_style = preferred_style
        self.min_candles = min_candles

        # Timeframe weights by style (higher = preferred)
        self.style_weights = {
            TimeFrameStyle.SCALPING: {"1m": 2.0, "5m": 1.5, "15m": 1.0, "1h": 0.5, "4h": 0.2, "1d": 0.1},
            TimeFrameStyle.INTRADAY: {"1m": 0.5, "5m": 1.0, "15m": 2.0, "1h": 2.0, "4h": 1.0, "1d": 0.5},
            TimeFrameStyle.SWING: {"1m": 0.1, "5m": 0.2, "15m": 0.5, "1h": 1.0, "4h": 2.0, "1d": 2.0},
        }

    def select_best_timeframe(
        self,
        timeframe_data: Dict[str, List[Candle]]
    ) -> Tuple[str, TimeFrameAnalysis]:
        """
        Analyze all timeframes and select the best one.

        Args:
            timeframe_data: Dict mapping timeframe -> list of candles

        Returns:
            (selected_timeframe, analysis_of_all_timeframes)
        """
        if not timeframe_data:
            raise ValueError("No timeframe data provided")

        # Analyze each timeframe
        analyses = {}
        for tf, candles in timeframe_data.items():
            if len(candles) >= self.min_candles:
                analyses[tf] = self._analyze_timeframe(candles, tf)

        if not analyses:
            # Fallback: return timeframe with most data
            tf_with_most_data = max(timeframe_data.keys(), key=lambda k: len(timeframe_data[k]))
            candles = timeframe_data[tf_with_most_data]
            return tf_with_most_data, self._analyze_timeframe(candles, tf_with_most_data)

        # Score and rank timeframes
        scored_tfs = []
        for tf, analysis in analyses.items():
            final_score = self._compute_final_score(analysis, tf)
            scored_tfs.append((tf, final_score, analysis))

        # Sort by score (highest first)
        scored_tfs.sort(key=lambda x: x[1], reverse=True)

        best_tf = scored_tfs[0][0]
        best_analysis = scored_tfs[0][2]

        # Add justification string
        best_analysis.reason = self._generate_justification(scored_tfs)

        return best_tf, best_analysis

    def _analyze_timeframe(self, candles: List[Candle], timeframe: str) -> TimeFrameAnalysis:
        """Analyze a single timeframe's quality."""
        if not candles:
            return TimeFrameAnalysis(
                timeframe=timeframe,
                noise_score=1.0,
                trend_strength=0.0,
                volatility_ratio=1.0,
                has_clear_structure=False,
                quality_score=0.0,
                reason="No data"
            )

        n = len(candles)
        idx = n - 1

        # Noise score (lower is better)
        noise_score = calculate_noise_score(candles, idx)

        # Trend strength
        trend_dir, trend_strength = detect_trend(candles, idx)

        # Volatility ratio
        atrs = compute_atr(candles, 14)
        valid_atrs = [a for a in atrs if not math.isnan(a)]
        if len(valid_atrs) >= 20:
            recent_atr = valid_atrs[-1]
            avg_atr = sum(valid_atrs[-20:]) / 20
            volatility_ratio = recent_atr / avg_atr if avg_atr > EPSILON else 1.0
        else:
            volatility_ratio = 1.0

        # Check for clear structure
        has_clear_structure = self._has_clear_structure(
            noise_score, trend_strength, volatility_ratio
        )

        # Quality score (0-1, higher is better)
        quality_score = self._compute_quality_score(
            noise_score, trend_strength, volatility_ratio, has_clear_structure
        )

        return TimeFrameAnalysis(
            timeframe=timeframe,
            noise_score=noise_score,
            trend_strength=trend_strength,
            volatility_ratio=volatility_ratio,
            has_clear_structure=has_clear_structure,
            quality_score=quality_score,
            reason=""
        )

    def _has_clear_structure(
        self,
        noise_score: float,
        trend_strength: float,
        volatility_ratio: float
    ) -> bool:
        """
        Determine if timeframe has clear market structure.

        Clear structure means:
        - Not too noisy (clean candles)
        - Either trending OR range-bound (not chop)
        - Volatility not extreme
        """
        # Noise check: lower is better
        noise_ok = noise_score < 0.6

        # Structure check: either trending or clear range
        trending = trend_strength > 0.3
        ranging = trend_strength < 0.15
        structure_ok = trending or ranging

        # Volatility check: avoid extreme conditions
        volatility_ok = 0.5 <= volatility_ratio <= 3.0

        return noise_ok and structure_ok and volatility_ok

    def _compute_quality_score(
        self,
        noise_score: float,
        trend_strength: float,
        volatility_ratio: float,
        has_clear_structure: bool
    ) -> float:
        """
        Compute overall quality score (0-1).

        Components:
        - Inverse noise (1 - noise_score): 40% weight
        - Trend strength OR range clarity: 30% weight
        - Optimal volatility (bell curve around 1.0): 30% weight
        """
        # Noise component (lower noise = higher score)
        noise_component = (1 - noise_score) * 0.4

        # Structure component
        if trend_strength > 0.2:
            # Trending: reward strength
            structure_component = min(1.0, trend_strength * 2) * 0.3
        else:
            # Ranging: reward stability
            structure_component = 0.25 * 0.3  # Moderate score for range

        # Volatility component (bell curve centered at 1.0)
        if 0.8 <= volatility_ratio <= 1.5:
            vol_component = 0.3
        elif 0.5 <= volatility_ratio < 0.8 or 1.5 < volatility_ratio <= 2.5:
            vol_component = 0.2
        else:
            vol_component = 0.1

        # Penalty for unclear structure
        if not has_clear_structure:
            vol_component *= 0.5

        quality = noise_component + structure_component + vol_component

        return min(1.0, max(0.0, quality))

    def _compute_final_score(
        self,
        analysis: TimeFrameAnalysis,
        timeframe: str
    ) -> float:
        """
        Compute final score incorporating style preference.

        Final score = quality_score * style_weight
        """
        style_weight = self.style_weights[self.preferred_style].get(timeframe, 1.0)
        return analysis.quality_score * style_weight

    def _generate_justification(self, scored_tfs: List[Tuple]) -> str:
        """Generate human-readable justification for selection."""
        best_tf, best_score, best_analysis = scored_tfs[0]

        reasons = []

        # Noise assessment
        if best_analysis.noise_score < 0.3:
            reasons.append("very clean candle structure")
        elif best_analysis.noise_score < 0.5:
            reasons.append("clean candle structure")
        else:
            reasons.append("acceptable candle structure")

        # Trend assessment
        if best_analysis.trend_strength > 0.5:
            reasons.append("strong trend")
        elif best_analysis.trend_strength > 0.2:
            reasons.append("moderate trend")
        elif best_analysis.trend_strength < 0.15:
            reasons.append("well-defined range")

        # Volatility assessment
        if 0.8 <= best_analysis.volatility_ratio <= 1.5:
            reasons.append("optimal volatility")
        elif best_analysis.volatility_ratio < 0.5:
            reasons.append("low volatility (may be slow)")
        elif best_analysis.volatility_ratio > 3.0:
            reasons.append("elevated volatility")

        # Style preference
        style_name = self.preferred_style.value
        reasons.append(f"suitable for {style_name} trading")

        return ", ".join(reasons).capitalize() + "."

    def get_all_analyses(
        self,
        timeframe_data: Dict[str, List[Candle]]
    ) -> Dict[str, TimeFrameAnalysis]:
        """
        Get analysis for all timeframes without selecting.

        Useful for debugging/visualization.
        """
        analyses = {}
        for tf, candles in timeframe_data.items():
            if len(candles) >= 20:  # Minimum for any analysis
                analyses[tf] = self._analyze_timeframe(candles, tf)
        return analyses
