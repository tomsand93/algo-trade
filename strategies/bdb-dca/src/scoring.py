"""
Scoring module: Symbol score, setup quality, and trade quality.

Symbol score [0-100]: composite of expectancy (35%), stability (25%),
liquidity proxy (15%), and sample size penalty (25%).

Setup quality [0-100]: scored at entry time using reversal bar strength,
distance below Alligator, squatbar presence, AO momentum, lowest bar position.

Trade quality [0-100]: scored post-trade using return quality, efficiency,
adverse excursion, DCA depth, and duration efficiency.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .models import BacktestResult, TradeRecord

MS_PER_DAY = 24 * 3600 * 1000


def _clip(lo: float, hi: float, val: float) -> float:
    return max(lo, min(hi, val))


# =============================================================================
# Symbol Score (4.1)
# =============================================================================

@dataclass
class SymbolScoreBreakdown:
    """Breakdown of symbol score components."""
    e_score: float = 0.0       # expectancy (35%)
    s_score: float = 0.0       # stability (25%)
    l_score: float = 0.0       # liquidity proxy (15%)
    p_score: float = 0.0       # sample size penalty (25%)
    composite: float = 0.0
    bracket: str = ""


def compute_symbol_score(result: BacktestResult,
                         reference_timestamp_ms: Optional[int] = None,
                         bars: Optional[list] = None) -> SymbolScoreBreakdown:
    """
    Compute symbol score [0-100].

    Args:
        result: BacktestResult with trades and equity_curve
        reference_timestamp_ms: "now" timestamp for lookback windows.
                                Defaults to last equity_curve timestamp.
        bars: Optional bar list for volume-based liquidity computation.
    """
    breakdown = SymbolScoreBreakdown()
    trades = result.trades
    equity_curve = result.equity_curve

    if not equity_curve:
        return breakdown

    if reference_timestamp_ms is None:
        reference_timestamp_ms = equity_curve[-1][0]

    # Build bar_index -> timestamp lookup from equity_curve
    idx_to_ts = {i: ts for i, (ts, _) in enumerate(equity_curve)}

    # Component 1: Recent Expectancy (E_score, 35%)
    breakdown.e_score = _expectancy_score(trades, reference_timestamp_ms, idx_to_ts)

    # Component 2: Stability (S_score, 25%)
    breakdown.s_score = _stability_score(equity_curve, reference_timestamp_ms)

    # Component 3: Liquidity Proxy (L_score, 15%)
    breakdown.l_score = _liquidity_score(bars, reference_timestamp_ms)

    # Component 4: Sample Size Penalty (P_score, 25%)
    breakdown.p_score = _sample_size_score(trades, reference_timestamp_ms, idx_to_ts)

    # Composite
    breakdown.composite = (
        0.35 * breakdown.e_score
        + 0.25 * breakdown.s_score
        + 0.15 * breakdown.l_score
        + 0.25 * breakdown.p_score
    )

    # Bracket
    s = breakdown.composite
    if s >= 80:
        breakdown.bracket = "Top tier"
    elif s >= 60:
        breakdown.bracket = "Acceptable"
    elif s >= 40:
        breakdown.bracket = "Cautionary"
    elif s >= 20:
        breakdown.bracket = "Poor"
    else:
        breakdown.bracket = "Dangerous"

    return breakdown


def _expectancy_score(trades: list[TradeRecord],
                      ref_ms: int, idx_to_ts: dict,
                      window_days: int = 30) -> float:
    """Component 1: Recent Expectancy, maps [-5, 5] -> [0, 100]."""
    cutoff = ref_ms - window_days * MS_PER_DAY
    recent = [t for t in trades if _trade_exit_ms(t, idx_to_ts) >= cutoff]

    n = len(recent)
    if n == 0:
        return 50.0  # neutral when no data

    wins = [t for t in recent if t.pnl_net > 0]
    losses = [t for t in recent if t.pnl_net <= 0]
    win_rate = len(wins) / n

    avg_win = sum(t.pnl_net for t in wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(t.pnl_net for t in losses) / len(losses)) if losses else 0.0

    if avg_loss == 0:
        expectancy_ratio = 10.0  # cap
    else:
        expectancy_ratio = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_loss

    e_raw = _clip(-5, 5, expectancy_ratio)
    return (e_raw + 5) / 10 * 100


def _stability_score(equity_curve: list, ref_ms: int) -> float:
    """Component 2: Stability from DD and daily PnL variance."""
    # Rolling 14-day max DD
    cutoff_14d = ref_ms - 14 * MS_PER_DAY
    recent_eq = [(ts, eq) for ts, eq in equity_curve if ts >= cutoff_14d]

    rolling_dd_pct = 0.0
    if len(recent_eq) >= 2:
        peak = 0.0
        for _, eq in recent_eq:
            if eq > peak:
                peak = eq
            if peak > 0:
                dd = (peak - eq) / peak * 100
                if dd > rolling_dd_pct:
                    rolling_dd_pct = dd

    dd_score = _clip(0, 100, 100 - rolling_dd_pct * 5)

    # Daily PnL std over 30 days
    cutoff_30d = ref_ms - 30 * MS_PER_DAY
    recent_30d = [(ts, eq) for ts, eq in equity_curve if ts >= cutoff_30d]

    daily_pnl_std = 0.0
    if len(recent_30d) >= 2:
        days = {}
        for ts, eq in recent_30d:
            dk = _day_key(ts)
            if dk not in days:
                days[dk] = {'start': eq, 'end': eq}
            days[dk]['end'] = eq

        daily_pcts = []
        for d in days.values():
            if d['start'] > 0:
                daily_pcts.append((d['end'] - d['start']) / d['start'] * 100)

        if len(daily_pcts) >= 2:
            mean = sum(daily_pcts) / len(daily_pcts)
            var = sum((x - mean) ** 2 for x in daily_pcts) / (len(daily_pcts) - 1)
            daily_pnl_std = math.sqrt(var) if var > 0 else 0.0

    var_score = _clip(0, 100, 100 - daily_pnl_std * 20)

    return 0.6 * dd_score + 0.4 * var_score


def _liquidity_score(bars: Optional[list], ref_ms: int,
                     window_days: int = 30) -> float:
    """Component 3: Liquidity proxy from median daily dollar volume."""
    if bars is None:
        return 50.0  # neutral when no bar data available

    cutoff = ref_ms - window_days * MS_PER_DAY
    recent_bars = [b for b in bars if b.timestamp >= cutoff]

    if not recent_bars:
        return 0.0

    # Aggregate daily dollar volume
    days = {}
    for b in recent_bars:
        dk = _day_key(b.timestamp)
        days[dk] = days.get(dk, 0.0) + b.close * b.volume

    daily_vols = sorted(days.values())
    if not daily_vols:
        return 0.0

    median_vol = daily_vols[len(daily_vols) // 2]
    l_raw = math.log10(max(1, median_vol))

    # Scale: log10(100K)=5 -> 33, log10(1M)=6 -> 67, log10(10M)=7 -> 100
    return _clip(0, 100, (l_raw - 4) / 3 * 100)


def _sample_size_score(trades: list[TradeRecord], ref_ms: int,
                       idx_to_ts: dict,
                       window_days: int = 60,
                       min_trades: int = 20,
                       min_threshold: int = 5) -> float:
    """Component 4: Sample size penalty."""
    cutoff = ref_ms - window_days * MS_PER_DAY
    n = sum(1 for t in trades if _trade_exit_ms(t, idx_to_ts) >= cutoff)

    if n < min_threshold:
        return 0.0

    return min(100.0, n / min_trades * 100)


# =============================================================================
# Setup Quality Score (4.2.1)
# =============================================================================

@dataclass
class SetupQualityBreakdown:
    """Breakdown of setup quality score components."""
    reversal_strength: float = 0.0
    depth_score: float = 0.0
    squat_score: float = 0.0
    ao_score: float = 0.0
    lookback_score: float = 0.0
    composite: float = 0.0


def compute_setup_quality(bar, indicators,
                          enable_ao: bool = False,
                          enable_mfi: bool = False) -> SetupQualityBreakdown:
    """
    Compute setup quality score at entry signal time.

    Args:
        bar: Current Bar object
        indicators: IndicatorState at this bar
        enable_ao: Whether AO filter is enabled
        enable_mfi: Whether MFI filter is enabled
    """
    bd = SetupQualityBreakdown()

    # 1. Reversal bar strength: close vs hl2 relative to bar range
    bar_range = bar.high - bar.low
    if bar_range > 0:
        close_vs_hl2_margin = (bar.close - bar.hl2) / bar_range
        bd.reversal_strength = _clip(0, 100, close_vs_hl2_margin / 0.3 * 100)

    # 2. Distance below Alligator
    if indicators.jaw is not None and indicators.teeth is not None and indicators.lips is not None:
        min_alligator = min(indicators.jaw, indicators.teeth, indicators.lips)
        if min_alligator > 0:
            distance_below_pct = (min_alligator - bar.high) / min_alligator * 100
            bd.depth_score = _clip(0, 100, distance_below_pct / 5 * 100)

    # 3. Squatbar presence
    hist = list(indicators.squatbar_history)
    if len(hist) >= 1 and hist[-1]:
        bd.squat_score = 100.0
    elif len(hist) >= 2 and hist[-2]:
        bd.squat_score = 70.0
    elif len(hist) >= 3 and hist[-3]:
        bd.squat_score = 40.0

    # 4. AO momentum
    if indicators.ao_diff is not None and indicators.atr_value is not None and indicators.atr_value > 0:
        ao_diff_normalized = abs(indicators.ao_diff) / indicators.atr_value
        bd.ao_score = _clip(0, 100, ao_diff_normalized / 0.5 * 100)

    # 5. Lowest bar lookback position
    if indicators.lowest_bars > 0:
        low_buf = list(indicators._low_buf)
        if len(low_buf) >= indicators.lowest_bars:
            window = low_buf[-indicators.lowest_bars:]
            current_low = bar.low
            bars_since_lower = 0
            for i in range(len(window) - 2, -1, -1):
                if window[i] < current_low:
                    bars_since_lower = len(window) - 1 - i
                    break
            else:
                bars_since_lower = indicators.lowest_bars
            bd.lookback_score = _clip(0, 100, bars_since_lower / indicators.lowest_bars * 100)

    # Weight redistribution when filters are disabled
    w_rev = 0.25
    w_depth = 0.25
    w_squat = 0.15
    w_ao = 0.20
    w_lookback = 0.15

    if not enable_ao and not enable_mfi:
        # Redistribute both AO and squat weights to reversal and depth
        w_rev = 0.25 + 0.10 + 0.075
        w_depth = 0.25 + 0.10 + 0.075
        w_squat = 0.0
        w_ao = 0.0
    elif not enable_ao:
        # Redistribute AO weight
        w_rev = 0.35
        w_depth = 0.35
        w_ao = 0.0
    elif not enable_mfi:
        # Redistribute squat weight
        w_rev = 0.325
        w_depth = 0.325
        w_squat = 0.0

    bd.composite = (
        w_rev * bd.reversal_strength
        + w_depth * bd.depth_score
        + w_squat * bd.squat_score
        + w_ao * bd.ao_score
        + w_lookback * bd.lookback_score
    )

    return bd


# =============================================================================
# Trade Quality Score (4.2.2)
# =============================================================================

@dataclass
class TradeQualityBreakdown:
    """Breakdown of trade quality score components."""
    return_score: float = 0.0
    efficiency_score: float = 0.0
    adversity_score: float = 0.0
    layer_score: float = 0.0
    duration_score: float = 0.0
    composite: float = 0.0


def compute_trade_quality(trade: TradeRecord,
                          symbol_avg_trade_pct: float,
                          symbol_avg_duration_hours: float,
                          max_layers: int,
                          highest_high: float,
                          lowest_low: float,
                          bar_interval_minutes: int = 30) -> TradeQualityBreakdown:
    """
    Compute trade quality score after round-trip closes.

    Args:
        trade: The completed TradeRecord
        symbol_avg_trade_pct: Historical avg trade % return for this symbol
        symbol_avg_duration_hours: Historical avg trade duration
        max_layers: Max DCA layers reached during this trade (1-4)
        highest_high: Highest high during the trade period
        lowest_low: Lowest low during the trade period
        bar_interval_minutes: Bar interval for duration calc
    """
    bd = TradeQualityBreakdown()

    entry_value = trade.entry_price * trade.entry_qty
    if entry_value <= 0:
        return bd

    net_pnl_pct = trade.pnl_net / entry_value * 100

    # 1. Return quality: net PnL vs expected
    ref_avg = max(0.1, abs(symbol_avg_trade_pct))
    return_vs_expected = net_pnl_pct / ref_avg
    bd.return_score = _clip(0, 100, return_vs_expected * 50)

    # 2. Efficiency: how much of available range was captured
    max_favorable = (highest_high - trade.entry_price) / trade.entry_price * 100
    capture_ratio = net_pnl_pct / max(0.01, max_favorable)
    bd.efficiency_score = _clip(0, 100, capture_ratio * 100)

    # 3. Adverse excursion
    max_adverse = (trade.entry_price - lowest_low) / trade.entry_price * 100
    bd.adversity_score = _clip(0, 100, 100 - max_adverse * 5)

    # 4. DCA depth
    layer_map = {1: 100, 2: 75, 3: 50, 4: 25}
    bd.layer_score = layer_map.get(max_layers, 25)

    # 5. Duration efficiency
    duration_hours = (trade.exit_bar_index - trade.entry_bar_index) * bar_interval_minutes / 60.0
    ref_dur = max(1, symbol_avg_duration_hours)
    duration_ratio = duration_hours / ref_dur
    bd.duration_score = _clip(0, 100, 100 - (duration_ratio - 1) * 50)

    # Composite
    bd.composite = (
        0.30 * bd.return_score
        + 0.20 * bd.efficiency_score
        + 0.20 * bd.adversity_score
        + 0.15 * bd.layer_score
        + 0.15 * bd.duration_score
    )

    return bd


# =============================================================================
# Helpers
# =============================================================================

def _trade_exit_ms(trade: TradeRecord, idx_to_ts: dict) -> int:
    """Get exit timestamp from bar index using equity_curve lookup."""
    return idx_to_ts.get(trade.exit_bar_index, trade.exit_bar_index)


def _day_key(timestamp_ms: int) -> str:
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")
