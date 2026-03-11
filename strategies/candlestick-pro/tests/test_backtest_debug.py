"""
Debug backtest to understand why no trades are executed.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import Candle, BacktestConfig, PatternType
from src.patterns import PatternDetector
from src.indicators import detect_support_resistance, compute_atr

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

# Detect S/R
sr_levels = detect_support_resistance(candles)
print(f"Detected {len(sr_levels)} S/R levels")
for sr in sr_levels:
    print(f"  {sr.level_type} at {sr.price} (strength: {sr.strength})")

# Initialize pattern detector
detector = PatternDetector()

# Walk through candles and try to detect patterns
patterns_found = 0
for i in range(50, len(candles)):
    result = detector.detect(
        candles[:i+1],  # Only historical data
        PatternType.ENGULFING,
        sr_levels,
        min_confidence=0.3
    )

    if result:
        patterns_found += 1
        print(f"\nPattern found at index {i}:")
        print(f"  Description: {result['pattern_description']}")
        print(f"  Direction: {result['direction']}")
        print(f"  Confidence: {result['confidence']:.2f}")
        print(f"  Context score: {result['context_score']:.2f}")
        print(f"  Invalidation: {result['invalidation_price']}")

        # Check if R:R would be sufficient
        if i + 1 < len(candles):
            entry = candles[i + 1].open
            sl = result['invalidation_price']
            risk = abs(entry - sl)
            reward = risk * 2.0  # Minimum target
            rr = reward / risk if risk > 0 else 0
            print(f"  Entry: {entry}, SL: {sl}, Risk: {risk:.2f}, RR: 1:{rr:.2f}")

print(f"\nTotal patterns found: {patterns_found}")
