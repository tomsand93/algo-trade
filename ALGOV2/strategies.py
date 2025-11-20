import pandas as pd
import numpy as np


# =========================
# ---  INDICATORS
# =========================

def compute_rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0).rolling(period).mean()
    down = -delta.clip(upper=0).rolling(period).mean()
    rs = up / down
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_macd(series):
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal


# =========================
# ---  STRATEGIES
# =========================

import pandas as pd
import numpy as np

# ================================
# Compute RSI
# ================================
def compute_rsi(series, length=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(length).mean()
    avg_loss = loss.rolling(length).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


# ================================
# RSI SIGNAL
# ================================
def rsi_signal(df):
    if len(df) < 20:
        return 0

    rsi = compute_rsi(df["close"])

    last = float(rsi.iloc[-1])  # FIX ✔ ensure scalar

    if last < 30:
        return 1  # BUY
    elif last > 70:
        return -1  # SELL
    return 0


SIGNAL_FUNCTIONS = {
    "RSI": rsi_signal,
}


def macd_signal(df):
    macd, signal = compute_macd(df["close"])
    if macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] <= signal.iloc[-2]:
        return "BUY"
    if macd.iloc[-1] < signal.iloc[-1] and macd.iloc[-2] >= signal.iloc[-2]:
        return "SELL"
    return None


def momentum_signal(df, period=10):
    close = df["close"]
    mom = close.iloc[-1] - close.iloc[-period]
    if mom > 0:
        return "BUY"
    if mom < 0:
        return "SELL"
    return None


def mean_reversion_signal(df):
    close = df["close"]
    sma = close.rolling(20).mean()
    std = close.rolling(20).std()

    upper = sma + 2 * std
    lower = sma - 2 * std

    if close.iloc[-1] < lower.iloc[-1]:
        return "BUY"
    if close.iloc[-1] > upper.iloc[-1]:
        return "SELL"
    return None


# =========================
# ---  EXPORTED COLLECTION
# =========================

SIGNAL_FUNCTIONS = {
    "RSI": rsi_signal,
    "MACD": macd_signal,
    "MOMENTUM": momentum_signal,
    "MEAN_REVERSION": mean_reversion_signal,
}

