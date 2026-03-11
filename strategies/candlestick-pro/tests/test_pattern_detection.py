"""
Test pattern detection directly.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import Candle, PatternType, SupportResistanceLevel
from src.patterns import PatternDetector
from src.indicators import compute_atr, detect_support_resistance


def test_pattern_detection():
    """Test pattern detection with obvious patterns."""

    # Create simple engulfing pattern
    candles = []
    base_time = 1704067200000

    # Create 20 leading candles for warmup
    price = 50000
    for i in range(30):
        candles.append(Candle(
            timestamp=base_time + i * 3600000,
            open=price,
            high=price + 50,
            low=price - 50,
            close=price - 30,
            volume=1000
        ))
        price -= 30

    # Create obvious bullish engulfing at index 30-31
    # Candle 30: Bearish
    candles.append(Candle(
        timestamp=base_time + 30 * 3600000,
        open=49000,
        high=49050,
        low=48800,
        close=48850,  # Bearish
        volume=1000
    ))

    # Candle 31: Bullish engulfing
    candles.append(Candle(
        timestamp=base_time + 31 * 3600000,
        open=48800,  # Opens below previous close
        high=49200,  # Goes above previous open
        low=48750,
        close=49150,  # Closes above previous open
        volume=2000
    ))

    print(f"Created {len(candles)} candles")
    print(f"\nPattern candles:")
    print(f"  Candle 30: O={candles[30].open}, H={candles[30].high}, L={candles[30].low}, C={candles[30].close}")
    print(f"    Bullish: {candles[30].is_bullish}, Body: {candles[30].body:.2f}")
    print(f"  Candle 31: O={candles[31].open}, H={candles[31].high}, L={candles[31].low}, C={candles[31].close}")
    print(f"    Bullish: {candles[31].is_bullish}, Body: {candles[31].body:.2f}")
    print(f"    Body ratio: {candles[31].body / candles[30].body:.2f}x")

    # Detect S/R
    sr_levels = detect_support_resistance(candles)
    print(f"\nDetected {len(sr_levels)} S/R levels")

    # If no S/R detected, create artificial ones at support level
    if not sr_levels:
        print("No S/R levels detected, creating artificial ones...")
        sr_levels.append(SupportResistanceLevel(
            price=48750,  # Near the pattern low
            level_type='support',
            strength=3,
            timestamp=candles[31].timestamp
        ))
        print(f"Created support at {sr_levels[0].price}")

    # Run pattern detector
    detector = PatternDetector()

    result = detector.detect(candles, PatternType.ENGULFING, sr_levels, min_confidence=0.3)

    if result:
        print(f"\n*** PATTERN DETECTED! ***")
        print(f"Pattern: {result['pattern']}")
        print(f"Description: {result['pattern_description']}")
        print(f"Direction: {result['direction']}")
        print(f"Confidence: {result['confidence']:.2f}")
        print(f"Checks: {result['checks']}")
    else:
        print(f"\n*** NO PATTERN DETECTED ***")

        # Debug: check individual conditions
        print("\n--- Debug ---")
        c1, c2 = candles[30], candles[31]
        print(f"c1.is_bullish: {c1.is_bullish}")
        print(f"c2.is_bullish: {c2.is_bullish}")
        print(f"Opposite colors: {c1.is_bullish != c2.is_bullish}")
        print(f"c2.body >= c1.body * 1.2: {c2.body >= c1.body * 1.2} ({c2.body:.2f} >= {c1.body * 1.2:.2f})")
        print(f"c2.open <= c1.close: {c2.open <= c1.close} ({c2.open} <= {c1.close})")
        print(f"c2.close >= c1.open: {c2.close >= c1.open} ({c2.close} >= {c1.open})")


if __name__ == '__main__':
    test_pattern_detection()
