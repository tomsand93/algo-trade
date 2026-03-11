"""
Candlestick Pro - Test with Obvious Patterns

Creates candles with very obvious engulfing patterns for testing.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import Candle
import csv


def create_obvious_engulfing_data():
    """Create data with very obvious engulfing patterns."""
    candles = []
    base_time = 1704067200000  # Jan 1, 2024
    price = 50000.0

    # Create 100 candles with multiple engulfing patterns
    for i in range(100):
        if i in [30, 50, 70]:  # Insert engulfing patterns at these indices
            # Bearish candle first
            c1 = Candle(
                timestamp=base_time + i * 3600000,
                open=price,
                high=price + 50,
                low=price - 200,
                close=price - 150,  # Bearish close
                volume=1000
            )
            candles.append(c1)
            price = c1.close

            # Bullish engulfing candle
            c2 = Candle(
                timestamp=base_time + (i + 1) * 3600000,
                open=price - 50,  # Open below c1 close
                high=price + 300,  # High above c1 open
                low=price - 100,
                close=price + 250,  # Bullish close, engulfs c1
                volume=2000
            )
            candles.append(c2)
            price = c2.close
            continue

        # Regular candles (random walk)
        import random
        random.seed(i)
        change = random.uniform(-200, 200)
        price += change

        high = price + abs(random.uniform(0, 100))
        low = price - abs(random.uniform(0, 100))
        open_p = low + random.uniform(0, high - low)
        close = low + random.uniform(0, high - low)

        candles.append(Candle(
            timestamp=base_time + i * 3600000,
            open=round(open_p, 2),
            high=round(high, 2),
            low=round(low, 2),
            close=round(close, 2),
            volume=1000
        ))
        price = close

    return candles


def save_candles(candles, filepath):
    """Save candles to CSV."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

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

    print(f"Saved {len(candles)} candles to {filepath.absolute()}")


if __name__ == '__main__':
    candles = create_obvious_engulfing_data()

    # Save test data
    save_candles(candles, '../data/obvious_engulfing.csv')

    # Print some info about the patterns we created
    print("\nPattern locations:")
    for i in [31, 51, 71]:  # The indices after our pattern inserts
        if i < len(candles):
            c = candles[i]
            print(f"  Candle {i}: O={c.open:.2f}, H={c.high:.2f}, L={c.low:.2f}, C={c.close:.2f}, Body={c.body:.2f}")
            if i > 0:
                prev = candles[i-1]
                print(f"    Prev:     O={prev.open:.2f}, H={prev.high:.2f}, L={prev.low:.2f}, C={prev.close:.2f}, Body={prev.body:.2f}")
                # Check if it engulfs
                if c.body > 0 and prev.body > 0:
                    print(f"    Body ratio: {c.body / prev.body:.2f}x")
