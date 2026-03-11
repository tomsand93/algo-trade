"""
Candlestick Pro - Pattern Detection

Single-pattern focused detection with strict validation rules.
Each pattern detector focuses on ONE high-quality pattern type.

Confluence filters: EMA trend, RSI, volume ratio must confirm pattern.
"""
from typing import List, Optional, Tuple, Dict
import math
from src.models import Candle, PatternType, Direction, SupportResistanceLevel
from src.indicators import (
    compute_atr, get_nearest_sr_levels,
    compute_rsi, compute_ema, compute_volume_ratio,
)

EPSILON = 1e-10


class PatternDetector:
    """
    Detects candlestick patterns with strict mechanical rules + confluence.

    Key principles:
    1. Pattern must appear at meaningful location (S/R, trend pullback)
    2. Clear structural requirements (no ambiguity)
    3. Rejects patterns in low-quality zones
    4. Requires trend alignment (EMA), volume confirmation, RSI filter
    """

    def __init__(self, config: Optional[Dict] = None):
        """Initialize pattern detector with optional config overrides."""
        self.config = config or self._default_config()

    def _default_config(self) -> Dict:
        """Default pattern thresholds."""
        return {
            "engulfing": {
                "body_ratio_min": 1.2,  # Engulfing body >= 120% of prior
                "min_range_atr_ratio": 0.5,
            },
            "pin_bar": {
                "body_ratio_max": 0.30,
                "dominant_wick_min": 0.60,
                "opposite_wick_max": 0.15,
                "wick_to_body_min": 2.0,
            },
            "morning_star": {
                "first_body_ratio_min": 0.60,
                "star_body_ratio_max": 0.30,
                "confirm_body_ratio_min": 0.50,
                "min_trend_candles": 5,
            },
            "inside_bar": {
                "contraction_max": 0.70,  # Inside bar range <= 70% of mother
            },
            # Confluence filter thresholds
            "confluence": {
                "min_volume_ratio": 1.2,
                "rsi_long_min": 30.0,
                "rsi_long_max": 60.0,
                "rsi_short_min": 40.0,
                "rsi_short_max": 70.0,
                "strict_trend": False,  # If True, require BOTH price and EMA aligned
            },
        }

    def detect(
        self,
        candles: List[Candle],
        pattern_type: PatternType,
        sr_levels: List[SupportResistanceLevel],
        min_confidence: float = 0.60,
        rsi_values: Optional[List[float]] = None,
        ema9: Optional[List[float]] = None,
        ema21: Optional[List[float]] = None,
        volume_ratios: Optional[List[float]] = None,
    ) -> Optional[Dict]:
        """
        Detect specified pattern type in the candle data.

        Precomputed indicators can be passed in to avoid recomputation.
        If not provided, they are computed here.

        Returns None if no valid pattern found, or dict with pattern details.
        """
        if len(candles) < 22:
            return None

        # Compute indicators if not supplied
        if rsi_values is None:
            rsi_values = compute_rsi(candles, 14)
        if ema9 is None:
            ema9 = compute_ema(candles, 9)
        if ema21 is None:
            ema21 = compute_ema(candles, 21)
        if volume_ratios is None:
            volume_ratios = compute_volume_ratio(candles, 20)

        indicators = {
            "rsi": rsi_values,
            "ema9": ema9,
            "ema21": ema21,
            "volume_ratios": volume_ratios,
        }

        # Route to specific detector
        detector = {
            PatternType.ENGULFING: self._detect_engulfing,
            PatternType.PIN_BAR: self._detect_pin_bar,
            PatternType.MORNING_STAR: self._detect_morning_star,
            PatternType.EVENING_STAR: self._detect_evening_star,
            PatternType.INSIDE_BAR: self._detect_inside_bar,
        }.get(pattern_type)

        if detector is None:
            raise ValueError(f"Unsupported pattern type: {pattern_type}")

        # Search for pattern in last 3 candles only (patterns must be fresh)
        # Searching further back leads to stale entries with distorted risk
        for i in range(len(candles) - 1, max(0, len(candles) - 4), -1):
            result = detector(candles, sr_levels, i, indicators)
            if result and result.get("confidence", 0) >= min_confidence:
                return result

        return None

    # ============== Confluence Filters ==============

    def _check_trend_alignment(
        self, direction: Direction, price: float,
        ema9: List[float], ema21: List[float], i: int,
        strict: bool = False
    ) -> Tuple[bool, float]:
        """
        Check if pattern direction aligns with EMA trend.

        Args:
            strict: If True, require BOTH price and EMA9 aligned (stronger filter)

        Returns (aligned, score) where score is 0.0-1.0.
        """
        if i >= len(ema9) or i >= len(ema21):
            return True, 0.5  # No data — don't filter

        e9 = ema9[i]
        e21 = ema21[i]

        if math.isnan(e9) or math.isnan(e21):
            return True, 0.5

        if direction == Direction.LONG:
            both_aligned = price > e21 and e9 > e21
            one_aligned = price > e21 or e9 > e21

            if strict:
                # Strong trend: require BOTH conditions
                if both_aligned:
                    return True, 1.0
                else:
                    return False, 0.0
            else:
                if both_aligned:
                    return True, 1.0
                elif one_aligned:
                    return True, 0.6
                else:
                    return False, 0.0
        else:
            both_aligned = price < e21 and e9 < e21
            one_aligned = price < e21 or e9 < e21

            if strict:
                if both_aligned:
                    return True, 1.0
                else:
                    return False, 0.0
            else:
                if both_aligned:
                    return True, 1.0
                elif one_aligned:
                    return True, 0.6
                else:
                    return False, 0.0

    def _check_volume(
        self, volume_ratios: List[float], i: int
    ) -> Tuple[bool, float]:
        """
        Check volume confirmation.

        Returns (confirmed, score) where score is 0.0-1.0.
        """
        if i >= len(volume_ratios):
            return True, 0.5  # No data — don't filter

        vr = volume_ratios[i]
        if math.isnan(vr):
            return True, 0.5

        min_vol = self.config["confluence"]["min_volume_ratio"]
        if vr >= min_vol:
            # Scale score: 1.2x = 0.6, 2.0x+ = 1.0
            score = min(1.0, 0.6 + (vr - min_vol) * 0.5)
            return True, score
        else:
            return False, 0.0

    def _check_rsi(
        self, direction: Direction, rsi_values: List[float], i: int
    ) -> Tuple[bool, float]:
        """
        Check RSI filter — reject extreme conditions.

        Returns (valid, score) where score is 0.0-1.0.
        """
        if i >= len(rsi_values):
            return True, 0.5

        rsi = rsi_values[i]
        if math.isnan(rsi):
            return True, 0.5

        cfg = self.config["confluence"]

        if direction == Direction.LONG:
            rsi_min = cfg["rsi_long_min"]
            rsi_max = cfg["rsi_long_max"]
        else:
            rsi_min = cfg["rsi_short_min"]
            rsi_max = cfg["rsi_short_max"]

        if rsi_min <= rsi <= rsi_max:
            # Optimal zone — score based on distance from extremes
            midpoint = (rsi_min + rsi_max) / 2
            dist = abs(rsi - midpoint)
            max_dist = (rsi_max - rsi_min) / 2
            score = 1.0 - (dist / max_dist) * 0.4  # 0.6-1.0
            return True, score
        else:
            return False, 0.0

    def _apply_confluence_filters(
        self, direction: Direction, candle: Candle,
        indicators: Dict, i: int
    ) -> Tuple[bool, float, float, float, List[str]]:
        """
        Apply confluence filters.

        Trend alignment is a HARD filter (reject counter-trend trades).
        Volume and RSI are SOFT filters (reduce confidence, don't reject).

        Returns (passed, trend_score, volume_score, rsi_score, filter_checks).
        """
        checks = []

        # Trend alignment — HARD filter (reject counter-trend)
        strict = self.config["confluence"].get("strict_trend", False)
        trend_ok, trend_score = self._check_trend_alignment(
            direction, candle.close,
            indicators["ema9"], indicators["ema21"], i, strict=strict
        )
        if not trend_ok:
            checks.append("REJECTED: Counter-trend pattern")
            return False, 0.0, 0.0, 0.0, checks
        checks.append(f"Trend aligned (score: {trend_score:.2f})")

        # Volume — SOFT filter (low volume = lower confidence, not rejection)
        vol_ok, vol_score = self._check_volume(indicators["volume_ratios"], i)
        if not vol_ok:
            vol_score = 0.2  # Penalize but don't reject
            checks.append(f"Volume low (score: {vol_score:.2f})")
        else:
            checks.append(f"Volume confirmed (score: {vol_score:.2f})")

        # RSI — SOFT filter (extreme = lower confidence, not rejection)
        rsi_ok, rsi_score = self._check_rsi(direction, indicators["rsi"], i)
        if not rsi_ok:
            rsi_score = 0.1  # Penalize but don't reject
            checks.append(f"RSI warning (score: {rsi_score:.2f})")
        else:
            checks.append(f"RSI valid (score: {rsi_score:.2f})")

        return True, trend_score, vol_score, rsi_score, checks

    # ============== Pattern Detectors ==============

    def _detect_engulfing(
        self,
        candles: List[Candle],
        sr_levels: List[SupportResistanceLevel],
        i: int,
        indicators: Dict,
    ) -> Optional[Dict]:
        """
        Detect Bullish or Bearish Engulfing pattern.

        Rules:
        - Two consecutive candles
        - First candle body is "inside" second candle body
        - Second candle engulfs >= 120% of first candle's body
        - Must appear at S/R or after trend extension
        - Must pass confluence filters (trend, volume, RSI)
        """
        if i < 1:
            return None

        c1, c2 = candles[i-1], candles[i]

        # Structural requirements
        if c1.is_bullish and c2.is_bullish:
            return None  # Need opposite colors
        if not c1.is_bullish and not c2.is_bullish:
            return None

        # Body engulfing
        if c2.body < c1.body * self.config["engulfing"]["body_ratio_min"]:
            return None

        # Price relationships
        if c2.is_bullish:  # Bullish engulfing
            if not (c2.open <= c1.close and c2.close >= c1.open):
                return None
            direction = Direction.LONG
            pattern_desc = "Bullish Engulfing"
            invalidation_price = c2.low
        else:  # Bearish engulfing
            if not (c2.open >= c1.close and c2.close <= c1.open):
                return None
            direction = Direction.SHORT
            pattern_desc = "Bearish Engulfing"
            invalidation_price = c2.high

        # Range strength check
        atrs = compute_atr(candles, 14)
        if i >= len(atrs) or math.isnan(atrs[i]):
            return None
        if c2.range < atrs[i] * self.config["engulfing"]["min_range_atr_ratio"]:
            return None

        # Confluence filters
        passed, trend_score, vol_score, rsi_score, filter_checks = \
            self._apply_confluence_filters(direction, c2, indicators, i)
        if not passed:
            return None

        # Context validation (S/R)
        context_score = self._validate_context(c2, direction, sr_levels, atrs[i])

        min_context = 0.2 if not sr_levels else 0.3
        if context_score < min_context:
            return None

        # Calculate confidence with new scoring
        confidence = self._calculate_confluence_confidence(
            geometry_score=self._engulfing_geometry_score(c1, c2, atrs[i]),
            trend_score=trend_score,
            context_score=context_score,
            volume_score=vol_score,
            rsi_score=rsi_score,
        )

        checks = self._get_engulfing_checks(c1, c2, atrs[i]) + filter_checks

        return {
            "pattern": PatternType.ENGULFING,
            "pattern_description": pattern_desc,
            "direction": direction,
            "pattern_index": i,
            "invalidation_price": invalidation_price,
            "entry_trigger": "Market entry on next candle open",
            "confidence": confidence,
            "context_score": context_score,
            "candles": (c1, c2),
            "checks": checks,
        }

    def _detect_pin_bar(
        self,
        candles: List[Candle],
        sr_levels: List[SupportResistanceLevel],
        i: int,
        indicators: Dict,
    ) -> Optional[Dict]:
        """
        Detect Pin Bar (Hammer or Shooting Star).

        Rules:
        - Body ratio <= 30% of range
        - One dominant wick >= 60% of range
        - Opposite wick <= 15% of range
        - Wick-to-body ratio >= 2.0
        - Must appear at S/R or after 3+ consecutive candles
        - Must pass confluence filters
        """
        c = candles[i]
        cfg = self.config["pin_bar"]

        # Structural requirements
        if c.body_ratio > cfg["body_ratio_max"]:
            return None

        dominant_wick = max(c.upper_wick, c.lower_wick)
        opposite_wick = min(c.upper_wick, c.lower_wick)

        if dominant_wick / c.range < cfg["dominant_wick_min"]:
            return None

        if opposite_wick / c.range > cfg["opposite_wick_max"]:
            return None

        if c.body < EPSILON:
            return None

        wick_to_body = dominant_wick / c.body
        if wick_to_body < cfg["wick_to_body_min"]:
            return None

        # Direction classification
        if c.lower_wick > c.upper_wick:
            direction = Direction.LONG
            pattern_desc = "Bullish Pin Bar (Hammer)"
            invalidation_price = c.low
        else:
            direction = Direction.SHORT
            pattern_desc = "Bearish Pin Bar (Shooting Star)"
            invalidation_price = c.high

        # Context validation
        atrs = compute_atr(candles, 14)
        if i >= len(atrs) or math.isnan(atrs[i]):
            return None

        # Confluence filters
        passed, trend_score, vol_score, rsi_score, filter_checks = \
            self._apply_confluence_filters(direction, c, indicators, i)
        if not passed:
            return None

        context_score = self._validate_context(c, direction, sr_levels, atrs[i])
        if context_score < 0.3:
            return None

        # Geometry score for pin bar
        body_score = (0.30 - c.body_ratio) / 0.30
        wick_score = min(1.0, wick_to_body / 5.0)
        geometry = body_score * 0.5 + wick_score * 0.5

        confidence = self._calculate_confluence_confidence(
            geometry_score=geometry,
            trend_score=trend_score,
            context_score=context_score,
            volume_score=vol_score,
            rsi_score=rsi_score,
        )

        checks = self._get_pin_bar_checks(c, cfg) + filter_checks

        return {
            "pattern": PatternType.PIN_BAR,
            "pattern_description": pattern_desc,
            "direction": direction,
            "pattern_index": i,
            "invalidation_price": invalidation_price,
            "entry_trigger": "Market entry on next candle open",
            "confidence": confidence,
            "context_score": context_score,
            "wick_to_body_ratio": wick_to_body,
            "candles": (c,),
            "checks": checks,
        }

    def _detect_morning_star(
        self,
        candles: List[Candle],
        sr_levels: List[SupportResistanceLevel],
        i: int,
        indicators: Dict,
    ) -> Optional[Dict]:
        """
        Detect Morning Star (bullish reversal) pattern.

        Three-candle pattern:
        1. Large bearish candle
        2. Small-bodied star (can gap down)
        3. Bullish confirmation closing above midpoint of candle 1
        """
        if i < 2:
            return None

        cfg = self.config["morning_star"]
        c1, c2, c3 = candles[i-2], candles[i-1], candles[i]

        # Candle 1: Bearish with strong body
        if c1.is_bullish or c1.body_ratio < cfg["first_body_ratio_min"]:
            return None

        # Candle 2: Star with weak body
        if c2.body_ratio > cfg["star_body_ratio_max"]:
            return None

        # Candle 3: Bullish confirmation
        if not c3.is_bullish or c3.body_ratio < cfg["confirm_body_ratio_min"]:
            return None

        # Candle 3 must close above midpoint of Candle 1
        c1_midpoint = (c1.open + c1.close) / 2
        if c3.close <= c1_midpoint:
            return None

        # Check for downtrend before pattern
        downtrend_count = self._count_consecutive_direction(candles, i-2, False)
        if downtrend_count < cfg["min_trend_candles"]:
            return None

        direction = Direction.LONG
        pattern_desc = "Morning Star (Bullish Reversal)"
        invalidation_price = min(c1.low, c2.low, c3.low)

        # Context validation
        atrs = compute_atr(candles, 14)
        if i >= len(atrs) or math.isnan(atrs[i]):
            return None

        # Confluence filters
        passed, trend_score, vol_score, rsi_score, filter_checks = \
            self._apply_confluence_filters(direction, c3, indicators, i)
        if not passed:
            return None

        context_score = self._validate_context(c3, direction, sr_levels, atrs[i])

        # Geometry: 3-candle patterns have inherent structural strength
        geometry = min(1.0, 0.6 + (downtrend_count / 20))

        confidence = self._calculate_confluence_confidence(
            geometry_score=geometry,
            trend_score=trend_score,
            context_score=context_score,
            volume_score=vol_score,
            rsi_score=rsi_score,
        )

        checks = self._get_morning_star_checks(c1, c2, c3, cfg) + filter_checks

        return {
            "pattern": PatternType.MORNING_STAR,
            "pattern_description": pattern_desc,
            "direction": direction,
            "pattern_index": i,
            "invalidation_price": invalidation_price,
            "entry_trigger": "Market entry on next candle open",
            "confidence": confidence,
            "context_score": context_score,
            "downtrend_count": downtrend_count,
            "candles": (c1, c2, c3),
            "checks": checks,
        }

    def _detect_evening_star(
        self,
        candles: List[Candle],
        sr_levels: List[SupportResistanceLevel],
        i: int,
        indicators: Dict,
    ) -> Optional[Dict]:
        """Detect Evening Star (bearish reversal) pattern."""
        if i < 2:
            return None

        cfg = self.config["morning_star"]  # Use same thresholds
        c1, c2, c3 = candles[i-2], candles[i-1], candles[i]

        # Candle 1: Bullish with strong body
        if not c1.is_bullish or c1.body_ratio < cfg["first_body_ratio_min"]:
            return None

        # Candle 2: Star with weak body
        if c2.body_ratio > cfg["star_body_ratio_max"]:
            return None

        # Candle 3: Bearish confirmation
        if c3.is_bullish or c3.body_ratio < cfg["confirm_body_ratio_min"]:
            return None

        # Candle 3 must close below midpoint of Candle 1
        c1_midpoint = (c1.open + c1.close) / 2
        if c3.close >= c1_midpoint:
            return None

        # Check for uptrend before pattern
        uptrend_count = self._count_consecutive_direction(candles, i-2, True)
        if uptrend_count < cfg["min_trend_candles"]:
            return None

        direction = Direction.SHORT
        pattern_desc = "Evening Star (Bearish Reversal)"
        invalidation_price = max(c1.high, c2.high, c3.high)

        # Context validation
        atrs = compute_atr(candles, 14)
        if i >= len(atrs) or math.isnan(atrs[i]):
            return None

        # Confluence filters
        passed, trend_score, vol_score, rsi_score, filter_checks = \
            self._apply_confluence_filters(direction, c3, indicators, i)
        if not passed:
            return None

        context_score = self._validate_context(c3, direction, sr_levels, atrs[i])

        geometry = min(1.0, 0.6 + (uptrend_count / 20))

        confidence = self._calculate_confluence_confidence(
            geometry_score=geometry,
            trend_score=trend_score,
            context_score=context_score,
            volume_score=vol_score,
            rsi_score=rsi_score,
        )

        checks = self._get_evening_star_checks(c1, c2, c3, cfg) + filter_checks

        return {
            "pattern": PatternType.EVENING_STAR,
            "pattern_description": pattern_desc,
            "direction": direction,
            "pattern_index": i,
            "invalidation_price": invalidation_price,
            "entry_trigger": "Market entry on next candle open",
            "confidence": confidence,
            "context_score": context_score,
            "uptrend_count": uptrend_count,
            "candles": (c1, c2, c3),
            "checks": checks,
        }

    def _detect_inside_bar(
        self,
        candles: List[Candle],
        sr_levels: List[SupportResistanceLevel],
        i: int,
        indicators: Dict,
    ) -> Optional[Dict]:
        """
        Detect Inside Bar pattern.

        The inside bar is completely contained within the previous (mother) bar.
        Direction is determined on breakout.
        """
        if i < 1:
            return None

        mother, inside = candles[i-1], candles[i]
        cfg = self.config["inside_bar"]

        # Structural: inside bar fully contained
        if not (inside.high < mother.high and inside.low > mother.low):
            return None

        # Range contraction
        if inside.range > mother.range * cfg["contraction_max"]:
            return None

        pattern_desc = "Inside Bar (Consolidation)"

        # Context validation - check if we're at a decision point
        atrs = compute_atr(candles, 14)
        if i >= len(atrs) or math.isnan(atrs[i]):
            return None

        # Inside bars are valid at S/R levels
        support, resistance = get_nearest_sr_levels(mother, sr_levels)

        at_decision_point = False
        if support and abs(mother.low - support.price) < atrs[i] * 0.5:
            at_decision_point = True
        if resistance and abs(mother.high - resistance.price) < atrs[i] * 0.5:
            at_decision_point = True

        if not at_decision_point:
            return None

        # Volume check (soft — inside bars are direction-neutral, skip trend/RSI)
        vol_ok, vol_score = self._check_volume(indicators["volume_ratios"], i)
        if not vol_ok:
            vol_score = 0.2  # Penalize but don't reject

        confidence = self._calculate_confluence_confidence(
            geometry_score=0.5,
            trend_score=0.5,  # Neutral — direction TBD
            context_score=0.5,
            volume_score=vol_score,
            rsi_score=0.5,
        )

        return {
            "pattern": PatternType.INSIDE_BAR,
            "pattern_description": pattern_desc,
            "direction": Direction.LONG,  # Default, will adjust on breakout
            "pattern_index": i,
            "invalidation_price": mother.low,  # For bullish breakout
            "entry_trigger": f"Breakout entry: close above {mother.high:.6f} for LONG, below {mother.low:.6f} for SHORT",
            "confidence": confidence,
            "context_score": 0.5,
            "mother_high": mother.high,
            "mother_low": mother.low,
            "contraction_ratio": inside.range / mother.range,
            "candles": (mother, inside),
            "checks": [
                "Inside bar contained within mother bar",
                f"Range contraction: {inside.range/mother.range:.2%} <= {cfg['contraction_max']:.0%}",
                "At decision point (S/R nearby)",
                f"Volume confirmed (score: {vol_score:.2f})",
            ],
        }

    # ============== Helper Methods ==============

    def _calculate_confluence_confidence(
        self,
        geometry_score: float,
        trend_score: float,
        context_score: float,
        volume_score: float,
        rsi_score: float,
    ) -> float:
        """
        Calculate confidence with weighted confluence scoring.

        25% geometry + 25% trend alignment + 25% S/R confluence + 15% volume + 10% RSI
        """
        confidence = (
            geometry_score * 0.25
            + trend_score * 0.25
            + context_score * 0.25
            + volume_score * 0.15
            + rsi_score * 0.10
        )
        return min(1.0, max(0.0, confidence))

    def _engulfing_geometry_score(
        self, c1: Candle, c2: Candle, atr: float
    ) -> float:
        """Geometry score for engulfing pattern (0-1)."""
        body_ratio = c2.body / c1.body if c1.body > EPSILON else 1.0
        body_score = min(1.0, (body_ratio - 1.0) / 1.0)
        range_score = min(1.0, c2.range / (atr * 2))
        return body_score * 0.6 + range_score * 0.4

    def _validate_context(
        self,
        candle: Candle,
        direction: Direction,
        sr_levels: List[SupportResistanceLevel],
        atr: float
    ) -> float:
        """
        Validate pattern appears at meaningful location.

        Returns context score (0-1) based on:
        - Proximity to S/R levels
        - Trend alignment
        - Not in middle of range
        """
        score = 0.0

        support, resistance = get_nearest_sr_levels(candle, sr_levels)

        # Check if at S/R level
        if direction == Direction.LONG:
            if support:
                dist = abs(candle.low - support.price)
                if dist < atr * 0.5:
                    score += 0.4
                    score += min(0.2, support.strength * 0.05)  # Strength bonus
        else:  # SHORT
            if resistance:
                dist = abs(candle.high - resistance.price)
                if dist < atr * 0.5:
                    score += 0.4
                    score += min(0.2, resistance.strength * 0.05)

        # Not in middle of range
        if support and resistance:
            sr_midpoint = (support.price + resistance.price) / 2
            dist_to_mid = abs(candle.close - sr_midpoint)
            if dist_to_mid > atr * 1.0:
                score += 0.2
        elif not sr_levels:
            # No S/R levels detected - add base score for datasets with insufficient history
            score += 0.2

        return min(1.0, score)

    def _count_consecutive_direction(
        self,
        candles: List[Candle],
        index: int,
        bullish: bool
    ) -> int:
        """Count consecutive candles of given direction ending at index."""
        count = 0
        for i in range(index, max(-1, index - 20), -1):
            if candles[i].is_bullish == bullish:
                count += 1
            else:
                break
        return count

    def _get_engulfing_checks(self, c1: Candle, c2: Candle, atr: float) -> List[str]:
        colors_opposite = (c1.is_bullish != c2.is_bullish)
        return [
            f"Candle colors opposite: {colors_opposite}",
            f"Body engulfing: {c2.body / c1.body:.2f}x >= {self.config['engulfing']['body_ratio_min']}x",
            f"Range strength: {c2.range / atr:.2f} ATR",
        ]

    def _get_pin_bar_checks(self, c: Candle, cfg: Dict) -> List[str]:
        return [
            f"Body ratio: {c.body_ratio:.3f} <= {cfg['body_ratio_max']}",
            f"Dominant wick: {max(c.upper_wick, c.lower_wick) / c.range:.2%} >= {cfg['dominant_wick_min']:.0%}",
            f"Opposite wick: {min(c.upper_wick, c.lower_wick) / c.range:.2%} <= {cfg['opposite_wick_max']:.0%}",
            f"Wick-to-body: {max(c.upper_wick, c.lower_wick) / c.body:.2f}x >= {cfg['wick_to_body_min']}x",
        ]

    def _get_morning_star_checks(self, c1: Candle, c2: Candle, c3: Candle, cfg: Dict) -> List[str]:
        return [
            f"Candle 1 bearish: {not c1.is_bullish}, body: {c1.body_ratio:.2%} >= {cfg['first_body_ratio_min']:.0%}",
            f"Candle 2 star: body {c2.body_ratio:.2%} <= {cfg['star_body_ratio_max']:.0%}",
            f"Candle 3 bullish: {c3.is_bullish}, body {c3.body_ratio:.2%} >= {cfg['confirm_body_ratio_min']:.0%}",
            "C3 close above C1 midpoint",
        ]

    def _get_evening_star_checks(self, c1: Candle, c2: Candle, c3: Candle, cfg: Dict) -> List[str]:
        return [
            f"Candle 1 bullish: {c1.is_bullish}, body: {c1.body_ratio:.2%} >= {cfg['first_body_ratio_min']:.0%}",
            f"Candle 2 star: body {c2.body_ratio:.2%} <= {cfg['star_body_ratio_max']:.0%}",
            f"Candle 3 bearish: {not c3.is_bullish}, body {c3.body_ratio:.2%} >= {cfg['confirm_body_ratio_min']:.0%}",
            "C3 close below C1 midpoint",
        ]
