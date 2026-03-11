"""
Direct backtest showing the system works.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import Candle, PatternType, Direction, BacktestConfig
from src.patterns import PatternDetector
from src.indicators import detect_support_resistance, compute_atr
import math

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

# Initialize components
detector = PatternDetector()
sr_levels = detect_support_resistance(candles)

# Backtest parameters
initial_capital = 100000
cash = initial_capital
position = None
trades = []
processed_pattern_indices = set()

print("\n" + "="*60)
print("BACKTEST EXECUTION")
print("="*60)

patterns_detected_count = 0
for i in range(50, len(candles)):
    # Check exit for existing position
    if position:
        sl = position['stop_loss']
        tp = position['take_profit']
        c = candles[i]

        if position['direction'] == Direction.LONG:
            if c.low <= sl:
                # Hit stop loss
                pnl = position['size'] * (sl - position['entry_price'])
                cash += pnl
                trades.append({
                    'entry': position['entry_price'],
                    'exit': sl,
                    'pnl': pnl,
                    'reason': 'Stop Loss'
                })
                print(f" [{i}] LONG closed at SL: {sl:.2f}, PnL: ${pnl:.2f}")
                position = None
                continue
            elif c.high >= tp:
                # Hit take profit
                pnl = position['size'] * (tp - position['entry_price'])
                cash += pnl
                trades.append({
                    'entry': position['entry_price'],
                    'exit': tp,
                    'pnl': pnl,
                    'reason': 'Take Profit'
                })
                print(f" [{i}] LONG closed at TP: {tp:.2f}, PnL: ${pnl:.2f}")
                position = None
                continue
        else:
            if c.high >= sl:
                pnl = position['size'] * (position['entry_price'] - sl)
                cash += pnl
                trades.append({
                    'entry': position['entry_price'],
                    'exit': sl,
                    'pnl': pnl,
                    'reason': 'Stop Loss'
                })
                print(f" [{i}] SHORT closed at SL: {sl:.2f}, PnL: ${pnl:.2f}")
                position = None
                continue
            elif c.low <= tp:
                pnl = position['size'] * (position['entry_price'] - tp)
                cash += pnl
                trades.append({
                    'entry': position['entry_price'],
                    'exit': tp,
                    'pnl': pnl,
                    'reason': 'Take Profit'
                })
                print(f" [{i}] SHORT closed at TP: {tp:.2f}, PnL: ${pnl:.2f}")
                position = None
                continue

    # Look for new pattern (only if no position)
    if position is None:
        pattern_result = detector.detect(
            candles[:i+1],
            PatternType.ENGULFING,
            sr_levels,
            min_confidence=0.3
        )

        if pattern_result:
            pattern_idx = pattern_result['pattern_index']
            patterns_detected_count += 1

            # Skip if we already processed this pattern
            if pattern_idx in processed_pattern_indices:
                continue

            processed_pattern_indices.add(pattern_idx)

            direction = pattern_result['direction']
            invalidation = pattern_result['invalidation_price']

            # Entry at next candle AFTER the pattern (pattern_idx + 1)
            # Use the truncated list for indexing
            truncated_candles = candles[:i+1]
            if pattern_idx + 1 >= len(truncated_candles):
                # Pattern was found at the end of current window, can't enter yet
                continue

            entry_candle_idx = pattern_idx + 1
            entry_price = truncated_candles[entry_candle_idx].open
            sl = invalidation

            # Calculate R:R
            if direction == Direction.LONG:
                sl = max(sl, entry_price - 1)  # Ensure SL below entry
                risk = entry_price - sl
                tp = entry_price + (risk * 2.0)  # 1:2 R:R
            else:
                sl = min(sl, entry_price + 1)  # Ensure SL above entry
                risk = sl - entry_price
                tp = entry_price - (risk * 2.0)

            rr = (abs(tp - entry_price) / risk) if risk > 0 else 0

            if rr < 2.0:
                print(f" [{i}] Pattern found at idx {pattern_idx}, but R:R {rr:.2f} < 2.0")
                continue

            # Calculate position size (1% risk)
            risk_amount = cash * 0.01
            size = risk_amount / risk if risk > 0 else 0

            if size <= 0:
                print(f" [{i}] Pattern found at idx {pattern_idx}, but size <= 0")
                continue

            # Enter position
            fee = size * entry_price * 0.001  # 0.1% fee
            if cash >= fee + size * entry_price:
                position = {
                    'entry_price': entry_price,
                    'size': size,
                    'direction': direction,
                    'stop_loss': sl,
                    'take_profit': tp,
                    'entry_index': entry_candle_idx,  # Store the actual entry index
                }
                cash -= (size * entry_price + fee)

                print(f"\n [{i}] NEW TRADE: {direction.value}")
                print(f"     Pattern Index: {pattern_idx}")
                print(f"     Entry Candle Index: {entry_candle_idx}")
                print(f"     Entry: {entry_price:.2f}")
                print(f"     SL: {sl:.2f}")
                print(f"     TP: {tp:.2f}")
                print(f"     Risk: ${risk:.2f}, Size: {size:.4f}")
                print(f"     R:R: 1:{rr:.2f}")
                print(f"     Cash after entry: ${cash:.2f}")

# Close any remaining position
if position:
    last_price = candles[-1].close
    pnl = position['size'] * (last_price - position['entry_price'])
    if position['direction'] == Direction.SHORT:
        pnl = -pnl
    cash += pnl
    trades.append({
        'entry': position['entry_price'],
        'exit': last_price,
        'pnl': pnl,
        'reason': 'End of data'
    })

# Calculate results
print("\n" + "="*60)
print("BACKTEST RESULTS")
print("="*60)

print(f"\nPatterns detected (including duplicates): {patterns_detected_count}")
print(f"Unique pattern indices processed: {len(processed_pattern_indices)}")
print(f"Pattern indices: {sorted(processed_pattern_indices)}")

winning_trades = [t for t in trades if t['pnl'] > 0]
losing_trades = [t for t in trades if t['pnl'] <= 0]

print(f"Total Trades: {len(trades)}")
print(f"Winning Trades: {len(winning_trades)}")
print(f"Losing Trades: {len(losing_trades)}")

if trades:
    win_rate = len(winning_trades) / len(trades)
    avg_win = sum(t['pnl'] for t in winning_trades) / len(winning_trades) if winning_trades else 0
    avg_loss = sum(t['pnl'] for t in losing_trades) / len(losing_trades) if losing_trades else 0
    total_return = (cash - initial_capital) / initial_capital

    print(f"Win Rate: {win_rate*100:.1f}%")
    print(f"Avg Win: ${avg_win:.2f}")
    print(f"Avg Loss: ${avg_loss:.2f}")
    print(f"Total Return: {total_return*100:.2f}%")
    print(f"Final Capital: ${cash:.2f}")

print("\nTrade Details:")
for i, t in enumerate(trades, 1):
    print(f"  {i}. {t['reason']}: Entry=${t['entry']:.2f}, Exit=${t['exit']:.2f}, PnL=${t['pnl']:.2f}")
