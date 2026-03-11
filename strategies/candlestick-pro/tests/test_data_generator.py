"""
Candlestick Pro - Test Data Generator

Generates realistic OHLCV data with embedded patterns for testing.
"""
import random
import math
import sys
from pathlib import Path
from typing import List, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import Candle


def generate_test_data(
    num_candles: int = 200,
    base_price: float = 50000.0,
    volatility: float = 0.002,
    include_patterns: bool = True
) -> List[Candle]:
    """
    Generate realistic test candlestick data.

    Args:
        num_candles: Number of candles to generate
        base_price: Starting price
        volatility: Price volatility factor
        include_patterns: Whether to embed specific patterns

    Returns:
        List of Candle objects
    """
    random.seed(42)
    candles = []
    price = base_price
    base_time = 1704067200000  # Jan 1, 2024

    # Generate initial trend
    trend_direction = 1
    trend_strength = 0.0005
    candles_in_trend = 0
    max_trend_length = random.randint(10, 20)

    for i in range(num_candles):
        # Update trend periodically
        candles_in_trend += 1
        if candles_in_trend >= max_trend_length:
            trend_direction *= -1
            candles_in_trend = 0
            max_trend_length = random.randint(8, 25)

        # Generate price movement
        trend_move = price * trend_strength * trend_direction
        random_move = price * volatility * random.gauss(0, 1)

        price_change = trend_move + random_move
        price += price_change

        # Generate OHLC
        high_low_range = abs(price * volatility * random.uniform(1.5, 3))
        high = price + high_low_range * random.uniform(0.3, 0.7)
        low = price - high_low_range * random.uniform(0.3, 0.7)

        open_price = low + random.random() * (high - low)
        close_price = low + random.random() * (high - low)

        # Bias close in trend direction
        if trend_direction > 0:
            close_price = low + random.uniform(0.5, 0.9) * (high - low)
        else:
            close_price = low + random.uniform(0.1, 0.5) * (high - low)

        volume = random.uniform(100, 10000)

        candle = Candle(
            timestamp=base_time + i * 3600000,  # 1 hour candles
            open=round(open_price, 2),
            high=round(high, 2),
            low=round(low, 2),
            close=round(close_price, 2),
            volume=round(volume, 2)
        )
        candles.append(candle)

        # Update price for next iteration
        price = close_price

    # Embed specific patterns if requested
    if include_patterns:
        candles = _embed_patterns(candles)

    return candles


def _embed_patterns(candles: List[Candle]) -> List[Candle]:
    """Embed specific patterns into the data for testing."""
    n = len(candles)

    # Embed bullish engulfing around index 50
    if n > 60:
        idx = 50
        base_close = candles[idx].close
        # Make candle idx bearish (small body)
        candles[idx].open = base_close + 50
        candles[idx].close = base_close - 30
        candles[idx].high = candles[idx].open + 20
        candles[idx].low = candles[idx].close - 20

        # Make candle idx+1 bullish engulfing
        candles[idx + 1].open = candles[idx].close - 10
        candles[idx + 1].close = candles[idx].open + 100
        candles[idx + 1].high = candles[idx + 1].close + 30
        candles[idx + 1].low = candles[idx].low - 20

    # Embed pin bar around index 100
    if n > 110:
        idx = 100
        # Create hammer at support
        candles[idx].open = candles[idx].close = candles[idx].high - 50
        candles[idx].low = candles[idx].open - 300  # Long lower wick
        candles[idx].high = candles[idx].open + 30  # Small upper wick

    # Embed morning star around index 150
    if n > 160:
        idx = 150
        # Candle 1: Strong bearish
        candles[idx].open = candles[idx].high
        candles[idx].close = candles[idx].low = candles[idx].high - 200

        # Candle 2: Small star (doji-like)
        candles[idx + 1].open = candles[idx].close - 20
        candles[idx + 1].close = candles[idx + 1].open + 10
        candles[idx + 1].high = candles[idx + 1].open + 30
        candles[idx + 1].low = candles[idx + 1].close - 20

        # Candle 3: Strong bullish confirmation
        candles[idx + 2].open = candles[idx + 1].close - 10
        candles[idx + 2].close = candles[idx].open + 100
        candles[idx + 2].high = candles[idx + 2].close + 20
        candles[idx + 2].low = candles[idx + 2].open - 10

    return candles


def save_test_data(filepath: str, num_candles: int = 500):
    """Generate and save test data to CSV."""
    candles = generate_test_data(num_candles=num_candles, include_patterns=True)

    import csv
    from pathlib import Path

    Path(filepath).parent.mkdir(parents=True, exist_ok=True)

    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        for candle in candles:
            writer.writerow([
                candle.timestamp,
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume
            ])

    print(f"Generated {len(candles)} test candles -> {filepath}")
    return candles


if __name__ == '__main__':
    # Generate test data
    candles = save_test_data('candlestick_pro/data/test_btc_1h.csv', 500)
    print(f"Price range: ${min(c.low for c in candles):.2f} - ${max(c.high for c in candles):.2f}")
