"""
Simple debug of pattern detection on full data.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import Candle, PatternType
from src.patterns import PatternDetector
from src.indicators import detect_support_resistance

# Load test data
candles = []
import csv
data_file = Path(__file__).parent / 'candlestick_pro' / 'data' / 'obvious_engulfing.csv'
with data_file.open('r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        candles.append(Candle(
            timestamp=int(row['timestamp']),
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close']),
            volume=float(row['volume'])
        ))

print(f"Loaded {len(candles)} candles")
print(f"Candle 30: O={candles[30].open:.2f}, H={candles[30].high:.2f}, L={candles[30].low:.2f}, C={candles[30].close:.2f}, Bull={candles[30].is_bullish}")
print(f"Candle 31: O={candles[31].open:.2f}, H={candles[31].high:.2f}, L={candles[31].low:.2f}, C={candles[31].close:.2f}, Bull={candles[31].is_bullish}")
print(f"  Body ratio: {candles[31].body / candles[30].body:.2f}x")

# Detect S/R
sr_levels = detect_support_resistance(candles)
print(f"\nDetected {len(sr_levels)} S/R levels")

# Initialize pattern detector
detector = PatternDetector()

# Try to detect pattern at index 31 (end of first engulfing pattern)
print(f"\nChecking pattern at index 31...")
result = detector.detect(
    candles,  # Full list
    PatternType.ENGULFING,
    sr_levels,
    min_confidence=0.3
)

if result:
    print(f"*** PATTERN DETECTED! ***")
    print(f"  Pattern: {result['pattern']}")
    print(f"  Description: {result['pattern_description']}")
    print(f"  Direction: {result['direction']}")
    print(f"  Index: {result['pattern_index']}")
    print(f"  Confidence: {result['confidence']:.2f}")
    print(f"  Context score: {result['context_score']:.2f}")
else:
    print(f"*** NO PATTERN DETECTED ***")

    # Check individual conditions manually
    c1, c2 = candles[30], candles[31]
    print(f"\n  Manual checks:")
    print(f"  c1.is_bullish: {c1.is_bullish}, c2.is_bullish: {c2.is_bullish}")
    print(f"  Opposite: {c1.is_bullish != c2.is_bullish}")
    print(f"  c2.body / c1.body: {c2.body / c1.body:.2f} >= 1.2: {c2.body >= c1.body * 1.2}")
    print(f"  c2.open <= c1.close: {c2.open <= c1.close} ({c2.open} <= {c1.close})")
    print(f"  c2.close >= c1.open: {c2.close >= c1.open} ({c2.close} >= {c1.open})")

    # Check ATR
    from src.indicators import compute_atr
    atrs = compute_atr(candles, 14)
    if len(atrs) > 31:
        print(f"  ATR[31]: {atrs[31]:.2f}")
        print(f"  c2.range >= ATR * 0.5: {c2.range >= atrs[31] * 0.5} ({c2.range} >= {atrs[31] * 0.5:.2f})")
