"""
Candlestick Pro - Technical Indicators

Implements ATR, trend detection, and support/resistance analysis.
"""
from typing import List, Tuple, Optional
import math
from src.models import Candle, SupportResistanceLevel

EPSILON = 1e-10


def compute_atr(candles: List[Candle], period: int = 14) -> List[float]:
    """
    Compute Average True Range using Wilder's smoothing method.

    Args:
        candles: List of candles
        period: ATR period (default 14)

    Returns:
        List of ATR values (NaN for candles before period)
    """
    n = len(candles)
    atr = [float('nan')] * n

    if n < period:
        return atr

    # Calculate initial True Range values
    true_ranges = []
    for i in range(1, period + 1):
        tr = max(
            candles[i].high - candles[i].low,
            abs(candles[i].high - candles[i-1].close),
            abs(candles[i].low - candles[i-1].close)
        )
        true_ranges.append(tr)

    # Initial ATR as simple average
    atr[period] = sum(true_ranges) / period

    # Wilder's smoothing for subsequent values
    for i in range(period + 1, n):
        tr = max(
            candles[i].high - candles[i].low,
            abs(candles[i].high - candles[i-1].close),
            abs(candles[i].low - candles[i-1].close)
        )
        atr[i] = (atr[i-1] * (period - 1) + tr) / period

    return atr


def detect_trend(candles: List[Candle], index: int, lookback: int = 20) -> Tuple[int, float]:
    """
    Detect trend direction and strength at given index.

    Returns:
        (direction, strength) where direction is -1 (bearish), 0 (neutral), 1 (bullish)
        and strength is 0-1 indicating trend strength
    """
    if index < lookback:
        return 0, 0.0

    start_idx = max(0, index - lookback)

    # Count consecutive directional candles
    bull_count = 0
    bear_count = 0
    for i in range(start_idx, index + 1):
        if candles[i].is_bullish:
            bull_count += 1
        else:
            bear_count += 1

    # Calculate price trend using linear regression slope
    closes = [candles[i].close for i in range(start_idx, index + 1)]
    n = len(closes)

    # Simple linear regression
    x_mean = (n - 1) / 2
    y_mean = sum(closes) / n

    numerator = sum((i - x_mean) * (closes[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator < EPSILON:
        slope = 0
    else:
        slope = numerator / denominator

    # Normalize slope by average price
    avg_price = y_mean
    normalized_slope = slope / avg_price if avg_price > EPSILON else 0

    # Determine direction and strength
    direction_strength = min(1.0, abs(normalized_slope) * 1000)  # Scale to 0-1

    if normalized_slope > 0.0005 and bull_count >= lookback * 0.6:
        return 1, direction_strength
    elif normalized_slope < -0.0005 and bear_count >= lookback * 0.6:
        return -1, direction_strength
    else:
        return 0, 0.0


def detect_support_resistance(
    candles: List[Candle],
    pivot_lookback: int = 10,
    pivot_left: int = 3,
    pivot_right: int = 3,
    cluster_threshold_pct: float = 0.005
) -> List[SupportResistanceLevel]:
    """
    Detect support and resistance levels using pivot points.

    Args:
        candles: List of candles
        pivot_lookback: How far back to look for pivots
        pivot_left: Left bars for pivot confirmation
        pivot_right: Right bars for pivot confirmation
        cluster_threshold_pct: Price clustering threshold (%)

    Returns:
        List of SupportResistanceLevel objects
    """
    n = len(candles)
    pivot_highs = []
    pivot_lows = []

    # Find pivot highs (local maxima) — search ALL candles, not just first N
    for i in range(pivot_left, n - pivot_right):
        is_pivot_high = all(
            candles[i].high > candles[j].high
            for j in range(i - pivot_left, i + pivot_right + 1)
            if j != i
        )
        if is_pivot_high:
            pivot_highs.append((i, candles[i].high))

    # Find pivot lows (local minima) — search ALL candles, not just first N
    for i in range(pivot_left, n - pivot_right):
        is_pivot_low = all(
            candles[i].low < candles[j].low
            for j in range(i - pivot_left, i + pivot_right + 1)
            if j != i
        )
        if is_pivot_low:
            pivot_lows.append((i, candles[i].low))

    # Cluster pivots into levels
    support_levels = _cluster_pivots(
        pivot_lows, candles, 'support', cluster_threshold_pct
    )
    resistance_levels = _cluster_pivots(
        pivot_highs, candles, 'resistance', cluster_threshold_pct
    )

    return support_levels + resistance_levels


def _cluster_pivots(
    pivots: List[Tuple[int, float]],
    candles: List[Candle],
    level_type: str,
    threshold_pct: float
) -> List[SupportResistanceLevel]:
    """Cluster nearby pivot points into support/resistance levels."""
    if not pivots:
        return []

    # Sort by price
    sorted_pivots = sorted(pivots, key=lambda x: x[1])

    clusters = []
    current_cluster = [sorted_pivots[0]]

    for idx, (i, price) in enumerate(sorted_pivots[1:], 1):
        avg_price = sum(p[1] for p in current_cluster) / len(current_cluster)
        diff_pct = abs(price - avg_price) / avg_price

        if diff_pct <= threshold_pct:
            current_cluster.append((i, price))
        else:
            clusters.append(current_cluster)
            current_cluster = [(i, price)]

    clusters.append(current_cluster)

    # Create levels from clusters (require at least 2 touches)
    levels = []
    for cluster in clusters:
        if len(cluster) >= 2:
            avg_level = sum(p[1] for p in cluster) / len(cluster)
            most_recent_idx = max(p[0] for p in cluster)

            levels.append(SupportResistanceLevel(
                price=avg_level,
                level_type=level_type,
                strength=len(cluster),
                timestamp=candles[most_recent_idx].timestamp
            ))

    return levels


def get_nearest_sr_levels(
    candle: Candle,
    sr_levels: List[SupportResistanceLevel]
) -> Tuple[Optional[SupportResistanceLevel], Optional[SupportResistanceLevel]]:
    """
    Get nearest support and resistance levels to a candle.

    Returns:
        (nearest_support, nearest_resistance)
    """
    supports = [lvl for lvl in sr_levels if lvl.level_type == 'support']
    resistances = [lvl for lvl in sr_levels if lvl.level_type == 'resistance']

    # Find closest levels
    nearest_support = None
    nearest_resistance = None

    if supports:
        nearest_support = min(supports, key=lambda lvl: abs(candle.low - lvl.price))

    if resistances:
        nearest_resistance = min(resistances, key=lambda lvl: abs(candle.high - lvl.price))

    return nearest_support, nearest_resistance


def calculate_noise_score(candles: List[Candle], index: int, lookback: int = 20) -> float:
    """
    Calculate market noise score (0-1, lower is cleaner).

    Considers:
    - Ratio of small body candles to total (dojis/spinning tops)
    - Directional consistency
    - Gap frequency
    """
    if index < lookback:
        return 1.0  # Maximum noise for insufficient data

    start = max(0, index - lookback)
    subset = candles[start:index + 1]

    # Small body candles (body < 30% of range)
    small_body_count = sum(1 for c in subset if c.body_ratio < 0.30)
    small_body_ratio = small_body_count / len(subset)

    # Directional changes
    direction_changes = 0
    for i in range(start + 1, index + 1):
        if candles[i].is_bullish != candles[i-1].is_bullish:
            direction_changes += 1
    change_ratio = direction_changes / max(1, index - start)

    # Combine scores (higher = more noise)
    noise = (small_body_ratio * 0.6 + change_ratio * 0.4)

    return min(1.0, max(0.0, noise))


def get_volatility_regime(candles: List[Candle], index: int, period: int = 50) -> str:
    """
    Classify current volatility regime.

    Returns:
        'low', 'normal', 'high', 'extreme'
    """
    if index < period:
        return 'normal'

    atrs = compute_atr(candles[:index + 1], 14)
    atrs = [a for a in atrs if not math.isnan(a)]

    if len(atrs) < period:
        return 'normal'

    recent_atr = atrs[-1]
    avg_atr = sum(atrs[-period:]) / period

    if recent_atr < avg_atr * 0.5:
        return 'low'
    elif recent_atr < avg_atr * 1.5:
        return 'normal'
    elif recent_atr < avg_atr * 2.5:
        return 'high'
    else:
        return 'extreme'


def compute_rsi(candles: List[Candle], period: int = 14) -> List[float]:
    """
    Compute Relative Strength Index using Wilder's smoothing.

    Returns list of RSI values (NaN for candles before period).
    RSI ranges 0-100: <30 oversold, >70 overbought.
    """
    n = len(candles)
    rsi = [float('nan')] * n

    if n < period + 1:
        return rsi

    # Calculate price changes
    gains = []
    losses = []
    for i in range(1, n):
        change = candles[i].close - candles[i - 1].close
        gains.append(max(0, change))
        losses.append(max(0, -change))

    # Initial average gain/loss (simple average of first `period` changes)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss < EPSILON:
        rsi[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi[period] = 100.0 - (100.0 / (1.0 + rs))

    # Wilder's smoothing for subsequent values
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period

        if avg_loss < EPSILON:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))

    return rsi


def compute_ema(candles: List[Candle], period: int) -> List[float]:
    """
    Compute Exponential Moving Average.

    Uses close prices. Returns NaN for candles before period.
    """
    n = len(candles)
    ema = [float('nan')] * n

    if n < period:
        return ema

    # Seed with SMA of first `period` candles
    sma = sum(candles[i].close for i in range(period)) / period
    ema[period - 1] = sma

    multiplier = 2.0 / (period + 1)

    for i in range(period, n):
        ema[i] = (candles[i].close - ema[i - 1]) * multiplier + ema[i - 1]

    return ema


def compute_volume_ratio(candles: List[Candle], period: int = 20) -> List[float]:
    """
    Compute ratio of current volume to average volume.

    Returns list of ratios (NaN if volume data missing or insufficient history).
    A ratio >= 1.2 suggests institutional participation.
    """
    n = len(candles)
    ratios = [float('nan')] * n

    if n < period:
        return ratios

    for i in range(period, n):
        current_vol = candles[i].volume
        if current_vol is None or current_vol <= 0:
            continue

        # Average volume over the lookback period (excluding current candle)
        vol_sum = 0.0
        vol_count = 0
        for j in range(i - period, i):
            if candles[j].volume is not None and candles[j].volume > 0:
                vol_sum += candles[j].volume
                vol_count += 1

        if vol_count < period * 0.5:
            continue  # Not enough volume data

        avg_vol = vol_sum / vol_count
        if avg_vol > EPSILON:
            ratios[i] = current_vol / avg_vol

    return ratios
