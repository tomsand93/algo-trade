"""
Candlestick Pro - Trade Manager

Handles dynamic entry, stop loss, and take profit calculations
based on price structure and volatility.
"""
from typing import List, Tuple, Optional
import math
from src.models import Candle, TradingIdea, Direction, PatternType, SupportResistanceLevel
from src.indicators import compute_atr, get_nearest_sr_levels

EPSILON = 1e-10


class TradeManager:
    """
    Calculates entry, stop loss, and take profit based on:

    1. Pattern invalidation level
    2. Recent swing highs/lows
    3. ATR-based buffer
    4. Support/resistance levels
    5. Risk-to-reward requirements (minimum 1:2)
    """

    def __init__(
        self,
        min_rr_ratio: float = 2.0,
        atr_sl_multiplier: float = 1.5,
        slippage_buffer_pct: float = 0.001
    ):
        self.min_rr_ratio = min_rr_ratio
        self.atr_sl_multiplier = atr_sl_multiplier
        self.slippage_buffer_pct = slippage_buffer_pct

    def create_trading_idea(
        self,
        pattern_result: dict,
        candles: List[Candle],
        sr_levels: List[SupportResistanceLevel],
        symbol: str,
        timeframe: str,
        timeframe_justification: str
    ) -> Optional[TradingIdea]:
        """
        Create a complete TradingIdea from pattern detection result.

        Returns None if R:R ratio is below minimum.
        """
        direction = pattern_result["direction"]
        invalidation_price = pattern_result["invalidation_price"]
        pattern_idx = pattern_result["pattern_index"]
        pattern_candles = pattern_result["candles"]

        # Get ATR for volatility reference
        atrs = compute_atr(candles, 14)
        if pattern_idx >= len(atrs) or math.isnan(atrs[pattern_idx]):
            return None
        atr = atrs[pattern_idx]

        # Calculate entry price (next candle open - no lookahead)
        if pattern_idx + 1 >= len(candles):
            entry_price = pattern_candles[-1].close
        else:
            entry_price = candles[pattern_idx + 1].open

        # Calculate dynamic stop loss
        sl_price, sl_reasoning = self._calculate_stop_loss(
            entry_price, invalidation_price, direction, atr, candles, pattern_idx
        )

        # Calculate dynamic take profit(s)
        tp_prices, tp_reasoning = self._calculate_take_profit(
            entry_price, sl_price, direction, atr, candles, pattern_idx, sr_levels
        )

        # Calculate risk/reward
        risk = abs(entry_price - sl_price)
        reward = abs(tp_prices[0] - entry_price)  # Primary TP
        rr_ratio = reward / risk if risk > EPSILON else 0

        # Check minimum R:R
        if rr_ratio < self.min_rr_ratio:
            return None

        # Get nearby S/R levels for context
        pattern_candle = pattern_candles[-1]
        nearby_support, nearby_resistance = get_nearest_sr_levels(pattern_candle, sr_levels)
        nearby_sr = []
        if nearby_support:
            nearby_sr.append(nearby_support)
        if nearby_resistance:
            nearby_sr.append(nearby_resistance)

        # Determine confidence level
        confidence_score = pattern_result.get("confidence", 0.5)
        if confidence_score >= 0.75:
            confidence_level = "High"
        elif confidence_score >= 0.5:
            confidence_level = "Medium"
        else:
            confidence_level = "Low"

        # Build trading idea
        return TradingIdea(
            symbol=symbol,
            selected_timeframe=timeframe,
            timeframe_justification=timeframe_justification,
            pattern=pattern_result["pattern"],
            pattern_description=pattern_result["pattern_description"],
            pattern_index=pattern_idx,
            direction=direction,
            entry_price=entry_price,
            entry_trigger=pattern_result["entry_trigger"],
            stop_loss_price=sl_price,
            stop_loss_reasoning=sl_reasoning,
            take_profit_prices=tp_prices,
            take_profit_reasoning=tp_reasoning,
            risk_amount=risk,
            reward_amount=reward,
            rr_ratio=rr_ratio,
            confidence_level=confidence_level,
            confidence_score=confidence_score,
            filters_passed=pattern_result.get("checks", []),
            atr_value=atr,
            sr_levels_nearby=nearby_sr,
            timestamp=pattern_candle.timestamp
        )

    def _calculate_stop_loss(
        self,
        entry_price: float,
        invalidation_price: float,
        direction: Direction,
        atr: float,
        candles: List[Candle],
        pattern_idx: int
    ) -> Tuple[float, str]:
        """
        Calculate dynamic stop loss based on:

        1. Pattern invalidation level
        2. Recent swing high/low
        3. ATR buffer
        """
        # Base SL at invalidation level
        if direction == Direction.LONG:
            base_sl = invalidation_price
        else:
            base_sl = invalidation_price

        # Check for nearby swing points
        swing_sl = self._find_swing_stop(candles, pattern_idx, direction)

        # Use the closer of the two (more conservative)
        if direction == Direction.LONG:
            # For longs: use higher SL (less risk)
            if swing_sl and swing_sl > base_sl:
                final_sl = swing_sl
                reasoning = f"Stop at swing low (${swing_sl:.6f}) - pattern invalidates if price breaks this level"
            else:
                # Add ATR buffer below pattern low
                final_sl = base_sl - (atr * 0.2)
                reasoning = f"Stop below pattern low (${base_sl:.6f}) with small ATR buffer - invalidates pattern structure"
        else:
            # For shorts: use lower SL (less risk)
            if swing_sl and swing_sl < base_sl:
                final_sl = swing_sl
                reasoning = f"Stop at swing high (${swing_sl:.6f}) - pattern invalidates if price breaks this level"
            else:
                # Add ATR buffer above pattern high
                final_sl = base_sl + (atr * 0.2)
                reasoning = f"Stop above pattern high (${base_sl:.6f}) with small ATR buffer - invalidates pattern structure"

        return final_sl, reasoning

    def _find_swing_stop(
        self,
        candles: List[Candle],
        pattern_idx: int,
        direction: Direction,
        lookback: int = 10
    ) -> Optional[float]:
        """Find recent swing high/low for stop loss placement."""
        start = max(0, pattern_idx - lookback)
        end = min(len(candles), pattern_idx + 1)

        if direction == Direction.LONG:
            # Find swing low (recent low point)
            swing_low = min(c.low for c in candles[start:end])
            return swing_low
        else:
            # Find swing high
            swing_high = max(c.high for c in candles[start:end])
            return swing_high

    def _calculate_take_profit(
        self,
        entry_price: float,
        stop_loss: float,
        direction: Direction,
        atr: float,
        candles: List[Candle],
        pattern_idx: int,
        sr_levels: List[SupportResistanceLevel]
    ) -> Tuple[List[float], str]:
        """
        Calculate dynamic take profit levels based on:

        1. Risk-to-reward ratio (minimum 1:2)
        2. Opposing structure (S/R levels)
        3. Multiple TP levels for partial profit taking
        """
        risk = abs(entry_price - stop_loss)

        # Primary TP at 1:2 R:R
        if direction == Direction.LONG:
            base_tp = entry_price + (risk * self.min_rr_ratio)
        else:
            base_tp = entry_price - (risk * self.min_rr_ratio)

        # Look for opposing S/R levels
        opposing_sr = self._find_opposing_sr(
            entry_price, direction, sr_levels, atr
        )

        tp_prices = []
        tp_reasoning_parts = []

        # TP1: Primary target at min R:R ratio (this is the exit used in backtest)
        tp_prices.append(base_tp)
        tp_reasoning_parts.append(f"TP1 at 1:{self.min_rr_ratio:.1f} R:R (${base_tp:.6f})")

        # TP2: Stretch target at opposing S/R or fixed 1:3 R:R
        if opposing_sr:
            dist_to_sr = abs(opposing_sr.price - entry_price)
            rr_to_sr = dist_to_sr / risk if risk > EPSILON else 0

            if rr_to_sr >= self.min_rr_ratio:
                tp_prices.append(opposing_sr.price)
                tp_reasoning_parts.append(f"TP2 at opposing {opposing_sr.level_type} (${opposing_sr.price:.6f}) at 1:{rr_to_sr:.1f} R:R")

        if len(tp_prices) < 2:
            tp2 = entry_price + (risk * 3.0) if direction == Direction.LONG else entry_price - (risk * 3.0)
            tp_prices.append(tp2)
            tp_reasoning_parts.append(f"TP2 at 1:3 R:R (${tp2:.6f})")

        tp_reasoning = ". ".join(tp_reasoning_parts) + "."

        return tp_prices, tp_reasoning

    def _find_opposing_sr(
        self,
        entry_price: float,
        direction: Direction,
        sr_levels: List[SupportResistanceLevel],
        atr: float
    ) -> Optional[SupportResistanceLevel]:
        """
        Find nearest opposing support/resistance level.

        For LONG: look for resistance above
        For SHORT: look for support below
        """
        if direction == Direction.LONG:
            # Find resistance above entry
            candidates = [
                lvl for lvl in sr_levels
                if lvl.level_type == 'resistance' and lvl.price > entry_price
            ]
            if candidates:
                return min(candidates, key=lambda lvl: lvl.price - entry_price)
        else:
            # Find support below entry
            candidates = [
                lvl for lvl in sr_levels
                if lvl.level_type == 'support' and lvl.price < entry_price
            ]
            if candidates:
                return min(candidates, key=lambda lvl: entry_price - lvl.price)

        return None

    def validate_filters(
        self,
        idea: TradingIdea,
        candles: List[Candle]
    ) -> Tuple[bool, List[str], List[str]]:
        """
        Validate trading idea against trade filters.

        Returns:
            (passed, passed_filters, failed_filters)
        """
        passed = True
        passed_filters = []
        failed_filters = []

        # Filter 1: Minimum R:R ratio
        if idea.rr_ratio >= self.min_rr_ratio:
            passed_filters.append(f"R:R ratio {idea.rr_ratio:.2f} >= {self.min_rr_ratio}")
        else:
            passed = False
            failed_filters.append(f"R:R ratio {idea.rr_ratio:.2f} < {self.min_rr_ratio}")

        # Filter 2: Volatility not too low or extreme
        if idea.atr_value > 0:
            recent_atr = idea.atr_value
            avg_range = sum(c.range for c in candles[-50:]) / min(50, len(candles))
            vol_ratio = recent_atr / avg_range if avg_range > EPSILON else 1.0

            if 0.5 <= vol_ratio <= 3.0:
                passed_filters.append(f"Volatility normal (ratio: {vol_ratio:.2f})")
            else:
                passed = False
                failed_filters.append(f"Volatility extreme (ratio: {vol_ratio:.2f})")

        # Filter 3: Not in middle of range (no clear S/R nearby)
        if idea.sr_levels_nearby:
            passed_filters.append(f"S/R confluence present")
        else:
            # Warning but not hard fail
            passed_filters.append(f"S/R weak (proceed with caution)")

        # Filter 4: Pattern at meaningful location
        if idea.confidence_score >= 0.5:
            passed_filters.append(f"Pattern confidence {idea.confidence_score:.0%} >= 50%")
        else:
            passed = False
            failed_filters.append(f"Pattern confidence {idea.confidence_score:.0%} < 50%")

        return passed, passed_filters, failed_filters
