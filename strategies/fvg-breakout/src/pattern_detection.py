"""
FVG Breakout Strategy - Pattern Detection Module
=================================================
Implements strict rule-based pattern recognition.
No discretion, no assumptions, no approximations.
"""

from dataclasses import dataclass
from typing import Optional, Literal
import pandas as pd

from src.config import StrategyConfig


@dataclass
class DailySetup:
    """Result of 09:30-09:35 analysis"""
    date: str
    symbol: str
    day_high: float
    day_low: float
    valid: bool = True


@dataclass
class FairValueGap:
    """Fair Value Gap (FVG) Pattern"""
    direction: Literal["long", "short"]
    gap_high: float      # Top of the gap
    gap_low: float       # Bottom of the gap
    candle_1_idx: int    # Index of first candle in sequence
    candle_2_idx: int    # Index of displacement candle
    candle_3_idx: int    # Index of third candle
    entry_trigger: float  # Price level for retest
    stop_loss: float      # SL at first FVG candle
    take_profit: float    # 3:1 R:R target
    valid: bool = True


@dataclass
class TradeSetup:
    """Complete trade setup with all conditions met"""
    date: str
    symbol: str
    direction: Literal["long", "short"]
    entry_price: float
    stop_loss: float
    take_profit: float
    entry_time: pd.Timestamp
    setup_type: str  # "FVG_BREAKOUT"
    valid: bool = True


class PatternDetector:
    """
    Detects FVG patterns with strict rule enforcement.

    Rules (NON-NEGOTIABLE):
    1. Day high/low from 09:30-09:35 5-min candle
    2. Break must occur after 09:35
    3. FVG must form after break
    4. Retest must occur into FVG
    5. Engulfing candle must confirm at retest
    """

    def __init__(self, risk_reward_ratio: float = 3.0, long_only: bool = False, config: StrategyConfig = None):
        self.risk_reward_ratio = risk_reward_ratio
        self.long_only = long_only  # If True, only take long trades
        self.config = config or StrategyConfig()  # Default = V1 behavior

    def get_daily_setup(self, data_5m: pd.DataFrame, date: str, symbol: str) -> Optional[DailySetup]:
        """
        Extract day_high and day_low from 09:30-09:35 candle.

        Args:
            data_5m: 5-minute DataFrame for the day
            date: Date string
            symbol: Symbol name

        Returns:
            DailySetup with high/low levels, or None if invalid
        """
        if data_5m.empty:
            return None

        # Find the 09:30 candle (first candle of regular session)
        data_5m = data_5m.between_time("09:30", "09:35")

        if data_5m.empty:
            return None

        # Get the first candle (09:30-09:35)
        first_candle = data_5m.iloc[0]

        return DailySetup(
            date=date,
            symbol=symbol,
            day_high=first_candle["high"],
            day_low=first_candle["low"],
            valid=True
        )

    def detect_break(self, current_price: float, daily_setup: DailySetup) -> Optional[Literal["long", "short"]]:
        """
        Detect if price has broken above day_high or below day_low.

        Args:
            current_price: Current price (1-minute close)
            daily_setup: Daily setup with day_high/day_low

        Returns:
            "long" if break above day_high, "short" if below day_low, None otherwise
        """
        if current_price > daily_setup.day_high:
            return "long"
        elif current_price < daily_setup.day_low:
            return "short"
        return None

    def detect_fvg(self, df_1m: pd.DataFrame, start_idx: int, direction: Literal["long", "short"]) -> Optional[FairValueGap]:
        """
        Detect Fair Value Gap formation after a break.

        FVG Definition:
        - 3-candle sequence
        - Candle #2 shows strong displacement
        - Gap between wick of #1 and wick of #3

        Args:
            df_1m: 1-minute DataFrame
            start_idx: Index to start looking (after break)
            direction: "long" or "short"

        Returns:
            FairValueGap object if valid pattern found, None otherwise
        """
        if start_idx + 2 >= len(df_1m):
            return None

        # Extract 3-candle sequence
        c1 = df_1m.iloc[start_idx]
        c2 = df_1m.iloc[start_idx + 1]
        c3 = df_1m.iloc[start_idx + 2]

        if direction == "long":
            # Bullish FVG: Gap between c1 high and c3 low
            # c2 must have strong upward displacement
            gap_high = c1["high"]
            gap_low = c3["low"]

            # Valid FVG requires actual gap
            if gap_low <= gap_high:
                return None  # No gap exists

            # Entry trigger at bottom of gap (retest level)
            entry_trigger = gap_low
            # SL placement: c1 (default) or c2 (tighter)
            if self.config.sl_placement == "c2":
                stop_loss = c2["low"]
            else:
                stop_loss = c1["low"]

        else:  # direction == "short"
            # Bearish FVG: Gap between c1 low and c3 high
            gap_low = c1["low"]
            gap_high = c3["high"]

            # Valid FVG requires actual gap
            if gap_high >= gap_low:
                return None  # No gap exists

            # Entry trigger at top of gap (retest level)
            entry_trigger = gap_high
            # SL placement: c1 (default) or c2 (tighter)
            if self.config.sl_placement == "c2":
                stop_loss = c2["high"]
            else:
                stop_loss = c1["high"]

        # ── V2 Quality Filters ──

        # 1. Minimum FVG gap size as % of price
        if self.config.min_fvg_gap_pct > 0:
            mid_price = (c2["high"] + c2["low"]) / 2
            gap_size = abs(gap_low - gap_high) if direction == "long" else abs(gap_low - gap_high)
            gap_pct = (gap_size / mid_price) * 100 if mid_price > 0 else 0
            if gap_pct < self.config.min_fvg_gap_pct:
                return None

        # 2. Displacement direction check (c2 must close in trade direction)
        if self.config.require_displacement_direction:
            if direction == "long" and c2["close"] <= c2["open"]:
                return None  # c2 not a bullish candle
            if direction == "short" and c2["close"] >= c2["open"]:
                return None  # c2 not a bearish candle

        # 3. Displacement body/range ratio (reject weak displacement candles)
        if self.config.min_displacement_body_ratio > 0:
            c2_range = c2["high"] - c2["low"]
            c2_body = abs(c2["close"] - c2["open"])
            if c2_range > 0:
                body_ratio = c2_body / c2_range
                if body_ratio < self.config.min_displacement_body_ratio:
                    return None

        # Calculate take profit at 3:1 R:R
        risk = abs(entry_trigger - stop_loss)
        reward = risk * self.risk_reward_ratio

        if direction == "long":
            take_profit = entry_trigger + reward
        else:
            take_profit = entry_trigger - reward

        return FairValueGap(
            direction=direction,
            gap_high=gap_high,
            gap_low=gap_low,
            candle_1_idx=start_idx,
            candle_2_idx=start_idx + 1,
            candle_3_idx=start_idx + 2,
            entry_trigger=entry_trigger,
            stop_loss=stop_loss,
            take_profit=take_profit,
            valid=True
        )

    def check_retest(self, df_1m: pd.DataFrame, fvg: FairValueGap, fvg_end_idx: int) -> bool:
        """
        Check if price retests into the FVG zone.

        Args:
            df_1m: 1-minute DataFrame
            fvg: FairValueGap object
            fvg_end_idx: Index where FVG completed (candle 3)

        Returns:
            True if retest occurred into FVG zone
        """
        # Look at candles after FVG formation
        for i in range(fvg_end_idx + 1, len(df_1m)):
            candle = df_1m.iloc[i]

            if fvg.direction == "long":
                # Bullish retest: candle range intersects gap zone
                # Spec: low(retest) <= low(C3) AND high(retest) >= high(C1)
                if candle["low"] <= fvg.entry_trigger and candle["high"] >= fvg.gap_high:
                    return True
            else:  # short
                # Bearish retest: candle range intersects gap zone
                # Spec: high(retest) >= high(C3) AND low(retest) <= low(C1)
                if candle["high"] >= fvg.entry_trigger and candle["low"] <= fvg.gap_low:
                    return True

        return False

    def detect_engulfing_at_retest(
        self,
        df_1m: pd.DataFrame,
        fvg: FairValueGap,
        retest_idx: int
    ) -> Optional[TradeSetup]:
        """
        Detect engulfing candle immediately after FVG retest.

        Entry Rules:
        - Engulfing candle must form immediately after retest
        - Must fully engulf previous retest candle
        - Must be in direction of trade

        Args:
            df_1m: 1-minute DataFrame
            fvg: FairValueGap object
            retest_idx: Index of retest candle

        Returns:
            TradeSetup if valid engulfing confirms, None otherwise
        """
        if retest_idx + 1 >= len(df_1m):
            return None

        retest_candle = df_1m.iloc[retest_idx]
        engulfing_candle = df_1m.iloc[retest_idx + 1]

        if fvg.direction == "long":
            # Bullish engulfing: trigger_close > trigger_open (green candle)
            if engulfing_candle["close"] <= engulfing_candle["open"]:
                return None  # Not a bullish candle

            # Strict engulfing: trigger_open < retest_close AND trigger_close > retest_open
            is_strict_engulfing = (
                engulfing_candle["open"] < retest_candle["close"] and
                engulfing_candle["close"] > retest_candle["open"]
            )

            # Relaxed entry: strong directional candle (body > ratio of range, closes up)
            is_relaxed_entry = False
            if self.config.relaxed_entry and not is_strict_engulfing:
                eng_range = engulfing_candle["high"] - engulfing_candle["low"]
                eng_body = abs(engulfing_candle["close"] - engulfing_candle["open"])
                if eng_range > 0 and (eng_body / eng_range) >= self.config.min_directional_body_ratio:
                    is_relaxed_entry = True

            if is_strict_engulfing or is_relaxed_entry:
                entry_price = engulfing_candle["close"]  # Enter on close
                take_profit = fvg.take_profit

                return TradeSetup(
                    date=df_1m.index[retest_idx].strftime("%Y-%m-%d"),
                    symbol="",  # To be filled
                    direction="long",
                    entry_price=entry_price,
                    stop_loss=fvg.stop_loss,
                    take_profit=take_profit,
                    entry_time=engulfing_candle.name,
                    setup_type="FVG_BREAKOUT"
                )

        else:  # short
            # Bearish engulfing: trigger_close < trigger_open (red candle)
            if engulfing_candle["close"] >= engulfing_candle["open"]:
                return None  # Not a bearish candle

            # Strict engulfing: trigger_open > retest_close AND trigger_close < retest_open
            is_strict_engulfing = (
                engulfing_candle["open"] > retest_candle["close"] and
                engulfing_candle["close"] < retest_candle["open"]
            )

            # Relaxed entry: strong directional candle (body > ratio of range, closes down)
            is_relaxed_entry = False
            if self.config.relaxed_entry and not is_strict_engulfing:
                eng_range = engulfing_candle["high"] - engulfing_candle["low"]
                eng_body = abs(engulfing_candle["close"] - engulfing_candle["open"])
                if eng_range > 0 and (eng_body / eng_range) >= self.config.min_directional_body_ratio:
                    is_relaxed_entry = True

            if is_strict_engulfing or is_relaxed_entry:
                entry_price = engulfing_candle["close"]  # Enter on close
                take_profit = fvg.take_profit

                return TradeSetup(
                    date=df_1m.index[retest_idx].strftime("%Y-%m-%d"),
                    symbol="",
                    direction="short",
                    entry_price=entry_price,
                    stop_loss=fvg.stop_loss,
                    take_profit=take_profit,
                    entry_time=engulfing_candle.name,
                    setup_type="FVG_BREAKOUT"
                )

        return None

    def _find_setup_for_direction(
        self,
        df_1m: pd.DataFrame,
        direction: Literal["long", "short"],
        break_idx: int,
        symbol: str
    ) -> Optional[TradeSetup]:
        """
        Search for complete FVG + retest + engulf after a confirmed break.

        Args:
            df_1m: 1-minute DataFrame (already time-filtered)
            direction: "long" or "short"
            break_idx: Index of the break candle
            symbol: Symbol name

        Returns:
            TradeSetup if all conditions met, None otherwise
        """
        for i in range(break_idx + 1, len(df_1m) - 2):
            fvg = self.detect_fvg(df_1m, i, direction)

            if fvg is not None:
                # FVG found, now look for retest + engulf
                for j in range(i + 3, len(df_1m)):
                    candle = df_1m.iloc[j]

                    is_retest = False
                    if direction == "long":
                        # Spec: low(retest) <= low(C3) AND high(retest) >= high(C1)
                        if candle["low"] <= fvg.entry_trigger and candle["high"] >= fvg.gap_high:
                            is_retest = True
                    else:
                        # Spec: high(retest) >= high(C3) AND low(retest) <= low(C1)
                        if candle["high"] >= fvg.entry_trigger and candle["low"] <= fvg.gap_low:
                            is_retest = True

                    if is_retest:
                        setup = self.detect_engulfing_at_retest(df_1m, fvg, j)
                        if setup is not None:
                            setup.symbol = symbol
                            return setup

        return None

    def find_trade_setup(
        self,
        df_1m: pd.DataFrame,
        daily_setup: DailySetup,
        after_time: str = "09:35"
    ) -> Optional[TradeSetup]:
        """
        Complete pattern detection pipeline. Checks BOTH directions
        and returns whichever complete signal sequence triggers first.

        Pipeline:
        1. Find first break in each direction (long and short)
        2. For each break, search for FVG → retest → engulf
        3. Return the setup with the earliest entry time

        Args:
            df_1m: 1-minute DataFrame
            daily_setup: Daily setup with levels
            after_time: Only look after this time

        Returns:
            TradeSetup if all conditions met, None otherwise
        """
        # Determine end time for entry window
        if self.config.entry_cutoff_time is not None:
            h, m = self.config.entry_cutoff_time
            end_time = f"{h:02d}:{m:02d}"
        else:
            end_time = "16:00"

        # Filter to after setup time
        df_1m = df_1m.between_time(after_time, end_time)

        if len(df_1m) < 5:
            return None

        # Find first break in each direction
        long_break_idx = None
        short_break_idx = None

        for i in range(len(df_1m)):
            current_close = df_1m.iloc[i]["close"]

            if long_break_idx is None and current_close > daily_setup.day_high:
                long_break_idx = i
            if short_break_idx is None and current_close < daily_setup.day_low:
                short_break_idx = i

        # Try both directions, collect completed setups
        candidates = []

        if long_break_idx is not None:
            setup = self._find_setup_for_direction(
                df_1m, "long", long_break_idx, daily_setup.symbol
            )
            if setup is not None:
                candidates.append(setup)

        if short_break_idx is not None and not self.long_only:
            setup = self._find_setup_for_direction(
                df_1m, "short", short_break_idx, daily_setup.symbol
            )
            if setup is not None:
                candidates.append(setup)

        if not candidates:
            return None

        # Return first completed signal (earliest entry time)
        candidates.sort(key=lambda s: s.entry_time)
        return candidates[0]


def validate_trading_window(timestamp: pd.Timestamp) -> bool:
    """
    Validate that timestamp is within allowed trading window.

    Rules:
    - No trades before 09:35 ET
    - No trades after 16:00 ET
    - Only regular NYSE session
    """
    time_only = timestamp.time()

    # Define time boundaries
    start = pd.Timestamp("09:35").time()
    end = pd.Timestamp("16:00").time()

    return start <= time_only <= end
