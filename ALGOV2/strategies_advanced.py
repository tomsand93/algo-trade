"""
Advanced Trading Strategies for Backtesting

Includes popular strategies:
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- Bollinger Bands
- SMA/EMA Crossover
- Mean Reversion
- Momentum
- VWAP
- Breakout
"""
import pandas as pd
import numpy as np


# =========================
# INDICATORS
# =========================

def compute_rsi(series, period=14):
    """Compute RSI indicator"""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_macd(series, fast=12, slow=26, signal=9):
    """Compute MACD indicator"""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram


def compute_bollinger_bands(series, period=20, std_dev=2):
    """Compute Bollinger Bands"""
    sma = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    return upper_band, sma, lower_band


def compute_ema(series, period):
    """Compute Exponential Moving Average"""
    return series.ewm(span=period, adjust=False).mean()


def compute_sma(series, period):
    """Compute Simple Moving Average"""
    return series.rolling(period).mean()


def compute_vwap(df):
    """Compute VWAP (Volume Weighted Average Price)"""
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    return (typical_price * df['volume']).cumsum() / df['volume'].cumsum()


# =========================
# TRADING STRATEGIES
# =========================

def rsi_strategy(df, rsi_period=14, oversold=30, overbought=70):
    """
    RSI Strategy
    Buy when RSI < oversold (default 30)
    Sell when RSI > overbought (default 70)
    """
    if len(df) < rsi_period + 5:
        return 0

    rsi = compute_rsi(df['close'], rsi_period)
    last_rsi = float(rsi.iloc[-1])

    if pd.isna(last_rsi):
        return 0

    if last_rsi < oversold:
        return 1  # BUY
    elif last_rsi > overbought:
        return -1  # SELL
    return 0  # HOLD


def macd_strategy(df, fast=12, slow=26, signal=9):
    """
    MACD Strategy
    Buy when MACD crosses above signal line
    Sell when MACD crosses below signal line
    """
    if len(df) < slow + signal + 5:
        return 0

    macd, signal_line, _ = compute_macd(df['close'], fast, slow, signal)

    if len(macd) < 2 or pd.isna(macd.iloc[-1]) or pd.isna(signal_line.iloc[-1]):
        return 0

    # Crossover detection
    if macd.iloc[-1] > signal_line.iloc[-1] and macd.iloc[-2] <= signal_line.iloc[-2]:
        return 1  # BUY (bullish crossover)
    elif macd.iloc[-1] < signal_line.iloc[-1] and macd.iloc[-2] >= signal_line.iloc[-2]:
        return -1  # SELL (bearish crossover)

    return 0  # HOLD


def bollinger_bands_strategy(df, period=20, std_dev=2):
    """
    Bollinger Bands Strategy
    Buy when price touches lower band
    Sell when price touches upper band
    """
    if len(df) < period + 5:
        return 0

    upper, middle, lower = compute_bollinger_bands(df['close'], period, std_dev)

    if pd.isna(upper.iloc[-1]) or pd.isna(lower.iloc[-1]):
        return 0

    current_price = df['close'].iloc[-1]

    # Buy at lower band, sell at upper band
    if current_price <= lower.iloc[-1]:
        return 1  # BUY
    elif current_price >= upper.iloc[-1]:
        return -1  # SELL

    return 0  # HOLD


def sma_crossover_strategy(df, short_period=50, long_period=200):
    """
    SMA Crossover Strategy (Golden Cross/Death Cross)
    Buy when short SMA crosses above long SMA (Golden Cross)
    Sell when short SMA crosses below long SMA (Death Cross)
    """
    if len(df) < long_period + 5:
        return 0

    sma_short = compute_sma(df['close'], short_period)
    sma_long = compute_sma(df['close'], long_period)

    if pd.isna(sma_short.iloc[-1]) or pd.isna(sma_long.iloc[-1]):
        return 0

    # Golden Cross
    if sma_short.iloc[-1] > sma_long.iloc[-1] and sma_short.iloc[-2] <= sma_long.iloc[-2]:
        return 1  # BUY
    # Death Cross
    elif sma_short.iloc[-1] < sma_long.iloc[-1] and sma_short.iloc[-2] >= sma_long.iloc[-2]:
        return -1  # SELL

    return 0  # HOLD


def ema_crossover_strategy(df, short_period=12, long_period=26):
    """
    EMA Crossover Strategy
    Buy when short EMA crosses above long EMA
    Sell when short EMA crosses below long EMA
    """
    if len(df) < long_period + 5:
        return 0

    ema_short = compute_ema(df['close'], short_period)
    ema_long = compute_ema(df['close'], long_period)

    if pd.isna(ema_short.iloc[-1]) or pd.isna(ema_long.iloc[-1]):
        return 0

    # Bullish crossover
    if ema_short.iloc[-1] > ema_long.iloc[-1] and ema_short.iloc[-2] <= ema_long.iloc[-2]:
        return 1  # BUY
    # Bearish crossover
    elif ema_short.iloc[-1] < ema_long.iloc[-1] and ema_short.iloc[-2] >= ema_long.iloc[-2]:
        return -1  # SELL

    return 0  # HOLD


def mean_reversion_strategy(df, period=20, num_std=2):
    """
    Mean Reversion Strategy
    Buy when price is > num_std standard deviations below mean
    Sell when price is > num_std standard deviations above mean
    """
    if len(df) < period + 5:
        return 0

    sma = compute_sma(df['close'], period)
    std = df['close'].rolling(period).std()

    if pd.isna(sma.iloc[-1]) or pd.isna(std.iloc[-1]):
        return 0

    current_price = df['close'].iloc[-1]
    upper_threshold = sma.iloc[-1] + (num_std * std.iloc[-1])
    lower_threshold = sma.iloc[-1] - (num_std * std.iloc[-1])

    if current_price < lower_threshold:
        return 1  # BUY (expecting reversion to mean)
    elif current_price > upper_threshold:
        return -1  # SELL (expecting reversion to mean)

    return 0  # HOLD


def momentum_strategy(df, period=10, threshold=0.02):
    """
    Momentum Strategy
    Buy when momentum > threshold
    Sell when momentum < -threshold
    """
    if len(df) < period + 5:
        return 0

    close = df['close']
    momentum = (close.iloc[-1] - close.iloc[-period]) / close.iloc[-period]

    if momentum > threshold:
        return 1  # BUY
    elif momentum < -threshold:
        return -1  # SELL

    return 0  # HOLD


def vwap_strategy(df):
    """
    VWAP Strategy
    Buy when price crosses above VWAP
    Sell when price crosses below VWAP
    """
    if len(df) < 20:
        return 0

    # Calculate VWAP for recent period
    recent_df = df.tail(100).copy()
    vwap = compute_vwap(recent_df)

    if pd.isna(vwap.iloc[-1]):
        return 0

    current_price = df['close'].iloc[-1]
    prev_price = df['close'].iloc[-2]

    # Crossover detection
    if current_price > vwap.iloc[-1] and prev_price <= vwap.iloc[-2]:
        return 1  # BUY
    elif current_price < vwap.iloc[-1] and prev_price >= vwap.iloc[-2]:
        return -1  # SELL

    return 0  # HOLD


def breakout_strategy(df, period=20):
    """
    Breakout Strategy
    Buy when price breaks above recent high
    Sell when price breaks below recent low
    """
    if len(df) < period + 5:
        return 0

    recent_high = df['high'].iloc[-period:-1].max()
    recent_low = df['low'].iloc[-period:-1].min()

    current_price = df['close'].iloc[-1]

    if current_price > recent_high:
        return 1  # BUY (breakout above resistance)
    elif current_price < recent_low:
        return -1  # SELL (breakdown below support)

    return 0  # HOLD


def triple_ema_strategy(df, fast=9, medium=21, slow=55):
    """
    Triple EMA Strategy
    Buy when fast > medium > slow (all trending up)
    Sell when fast < medium < slow (all trending down)
    """
    if len(df) < slow + 5:
        return 0

    ema_fast = compute_ema(df['close'], fast)
    ema_medium = compute_ema(df['close'], medium)
    ema_slow = compute_ema(df['close'], slow)

    if pd.isna(ema_fast.iloc[-1]) or pd.isna(ema_medium.iloc[-1]) or pd.isna(ema_slow.iloc[-1]):
        return 0

    # Bullish alignment
    if ema_fast.iloc[-1] > ema_medium.iloc[-1] > ema_slow.iloc[-1]:
        # Check if this is a new crossover
        if not (ema_fast.iloc[-2] > ema_medium.iloc[-2] > ema_slow.iloc[-2]):
            return 1  # BUY
    # Bearish alignment
    elif ema_fast.iloc[-1] < ema_medium.iloc[-1] < ema_slow.iloc[-1]:
        # Check if this is a new crossover
        if not (ema_fast.iloc[-2] < ema_medium.iloc[-2] < ema_slow.iloc[-2]):
            return -1  # SELL

    return 0  # HOLD


# =========================
# STRATEGY REGISTRY
# =========================

STRATEGIES = {
    "RSI": rsi_strategy,
    "MACD": macd_strategy,
    "BOLLINGER_BANDS": bollinger_bands_strategy,
    "SMA_CROSSOVER": sma_crossover_strategy,
    "EMA_CROSSOVER": ema_crossover_strategy,
    "MEAN_REVERSION": mean_reversion_strategy,
    "MOMENTUM": momentum_strategy,
    "VWAP": vwap_strategy,
    "BREAKOUT": breakout_strategy,
    "TRIPLE_EMA": triple_ema_strategy,
}
