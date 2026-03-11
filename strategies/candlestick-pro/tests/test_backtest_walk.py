"""
Debug backtest execution.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import Candle, PatternType, BacktestConfig
from src.patterns import PatternDetector
from src.indicators import detect_support_resistance
from src.strategy import CandlestickStrategy

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

# Initialize strategy
strategy = CandlestickStrategy(
    pattern_type=PatternType.ENGULFING,
    min_rr_ratio=2.0,
    min_confidence=0.3
)

# Detect S/R on full dataset
sr_levels = detect_support_resistance(candles)
print(f"Detected {len(sr_levels)} S/R levels")

# Walk through like backtest does
patterns_found = []
for i in range(50, len(candles)):
    truncated = candles[:i+1]
    result = strategy.pattern_detector.detect(
        truncated,
        PatternType.ENGULFING,
        sr_levels,
        min_confidence=0.3
    )

    if result:
        patterns_found.append((i, result))
        print(f"\nPattern found when i={i}:")
        print(f"  Truncated list length: {len(truncated)}")
        print(f"  Pattern index: {result['pattern_index']}")
        print(f"  Confidence: {result['confidence']:.2f}")
        print(f"  Context: {result['context_score']:.2f}")

        # Check entry and R:R
        if i + 1 < len(candles):
            entry = candles[i + 1].open
            sl = result['invalidation_price']
            risk = abs(entry - sl)
            rr = 2.0  # Minimum target
            print(f"  Entry (next candle): {entry}")
            print(f"  SL: {sl}")
            print(f"  Risk: {risk:.2f}")
            print(f"  R:R would be: 1:{rr:.2f}")

print(f"\n\nTotal patterns found during walk: {len(patterns_found)}")
