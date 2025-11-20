"""
Trading Strategies Collection

All strategies return:
    1 = BUY signal
   -1 = SELL signal
    0 = HOLD (no action)
"""
import pandas as pd
import numpy as np


# ============================================================
# TECHNICAL INDICATORS
# ============================================================

def compute_rsi(series, period=14):
    """Calculate RSI (Relative Strength Index)"""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_macd(series, fast=12, slow=26, signal=9):
    """Calculate MACD (Moving Average Convergence Divergence)"""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram


def compute_bollinger_bands(series, period=20, std_dev=2):
    """Calculate Bollinger Bands"""
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return upper, sma, lower


def compute_sma(series, period):
    """Calculate Simple Moving Average"""
    return series.rolling(window=period).mean()


def compute_ema(series, period):
    """Calculate Exponential Moving Average"""
    return series.ewm(span=period, adjust=False).mean()


def compute_vwap(df):
    """Calculate VWAP (Volume Weighted Average Price)"""
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    return (typical_price * df['volume']).cumsum() / df['volume'].cumsum()


# ============================================================
# STRATEGY 1: RSI
# ============================================================

def rsi_strategy(df, period=14, oversold=30, overbought=70):
    """
    RSI Strategy

    Buy when RSI < oversold (default 30)
    Sell when RSI > overbought (default 70)
    """
    if len(df) < period + 5:
        return 0

    rsi = compute_rsi(df['close'], period)
    last_rsi = float(rsi.iloc[-1])

    if pd.isna(last_rsi):
        return 0

    if last_rsi < oversold:
        return 1  # BUY
    elif last_rsi > overbought:
        return -1  # SELL
    return 0


# ============================================================
# STRATEGY 2: MACD
# ============================================================

def macd_strategy(df, fast=12, slow=26, signal=9):
    """
    MACD Strategy

    Buy when MACD crosses above signal line
    Sell when MACD crosses below signal line
    """
    if len(df) < slow + signal + 5:
        return 0

    macd, signal_line, _ = compute_macd(df['close'], fast, slow, signal)

    if len(macd) < 2:
        return 0

    # Bullish crossover
    if macd.iloc[-1] > signal_line.iloc[-1] and macd.iloc[-2] <= signal_line.iloc[-2]:
        return 1
    # Bearish crossover
    elif macd.iloc[-1] < signal_line.iloc[-1] and macd.iloc[-2] >= signal_line.iloc[-2]:
        return -1

    return 0


# ============================================================
# STRATEGY 3: BOLLINGER BANDS
# ============================================================

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

    price = df['close'].iloc[-1]

    if price <= lower.iloc[-1]:
        return 1  # BUY
    elif price >= upper.iloc[-1]:
        return -1  # SELL

    return 0


# ============================================================
# STRATEGY 4: SMA CROSSOVER
# ============================================================

def sma_crossover_strategy(df, short_period=50, long_period=200):
    """
    SMA Crossover (Golden Cross / Death Cross)

    Buy when short SMA crosses above long SMA
    Sell when short SMA crosses below long SMA
    """
    if len(df) < long_period + 5:
        return 0

    sma_short = compute_sma(df['close'], short_period)
    sma_long = compute_sma(df['close'], long_period)

    if pd.isna(sma_short.iloc[-1]) or pd.isna(sma_long.iloc[-1]):
        return 0

    # Golden Cross
    if sma_short.iloc[-1] > sma_long.iloc[-1] and sma_short.iloc[-2] <= sma_long.iloc[-2]:
        return 1
    # Death Cross
    elif sma_short.iloc[-1] < sma_long.iloc[-1] and sma_short.iloc[-2] >= sma_long.iloc[-2]:
        return -1

    return 0


# ============================================================
# STRATEGY 5: EMA CROSSOVER
# ============================================================

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
        return 1
    # Bearish crossover
    elif ema_short.iloc[-1] < ema_long.iloc[-1] and ema_short.iloc[-2] >= ema_long.iloc[-2]:
        return -1

    return 0


# ============================================================
# STRATEGY 6: MEAN REVERSION
# ============================================================

def mean_reversion_strategy(df, period=20, num_std=2):
    """
    Mean Reversion Strategy

    Buy when price is below mean by N standard deviations
    Sell when price is above mean by N standard deviations
    """
    if len(df) < period + 5:
        return 0

    sma = compute_sma(df['close'], period)
    std = df['close'].rolling(window=period).std()

    if pd.isna(sma.iloc[-1]) or pd.isna(std.iloc[-1]):
        return 0

    price = df['close'].iloc[-1]
    upper = sma.iloc[-1] + (num_std * std.iloc[-1])
    lower = sma.iloc[-1] - (num_std * std.iloc[-1])

    if price < lower:
        return 1  # BUY
    elif price > upper:
        return -1  # SELL

    return 0


# ============================================================
# STRATEGY 7: MOMENTUM
# ============================================================

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

    return 0


# ============================================================
# STRATEGY 8: VWAP
# ============================================================

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

    price_curr = df['close'].iloc[-1]
    price_prev = df['close'].iloc[-2]

    # Crossover detection
    if price_curr > vwap.iloc[-1] and price_prev <= vwap.iloc[-2]:
        return 1  # BUY
    elif price_curr < vwap.iloc[-1] and price_prev >= vwap.iloc[-2]:
        return -1  # SELL

    return 0


# ============================================================
# STRATEGY 9: BREAKOUT
# ============================================================

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

    price = df['close'].iloc[-1]

    if price > recent_high:
        return 1  # BUY
    elif price < recent_low:
        return -1  # SELL

    return 0


# ============================================================
# STRATEGY 10: TRIPLE EMA
# ============================================================

def triple_ema_strategy(df, fast=9, medium=21, slow=55):
    """
    Triple EMA Strategy

    Buy when fast > medium > slow (bullish alignment)
    Sell when fast < medium < slow (bearish alignment)
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
        # Check if new crossover
        if not (ema_fast.iloc[-2] > ema_medium.iloc[-2] > ema_slow.iloc[-2]):
            return 1  # BUY

    # Bearish alignment
    elif ema_fast.iloc[-1] < ema_medium.iloc[-1] < ema_slow.iloc[-1]:
        # Check if new crossover
        if not (ema_fast.iloc[-2] < ema_medium.iloc[-2] < ema_slow.iloc[-2]):
            return -1  # SELL

    return 0


# ============================================================
# STRATEGY REGISTRY
# ============================================================

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
