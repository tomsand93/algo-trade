"""
Simplified backtest that works correctly.
Enter trade when pattern is found, execute at NEXT candle.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import Candle, PatternType, Direction
from src.patterns import PatternDetector
from src.indicators import detect_support_resistance
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
pending_entry = None  # Store entry info for next candle

print("\n" + "="*60)
print("BACKTEST EXECUTION")
print("="*60)

for i in range(20, len(candles)):
    c = candles[i]

    # Execute pending entry
    if pending_entry:
        entry_info = pending_entry
        pending_entry = None

        entry_price = c.open
        direction = entry_info['direction']
        invalidation = entry_info['invalidation']
        pattern_idx = entry_info['pattern_idx']

        # Calculate SL and TP
        # For LONG: SL must be below entry, for SHORT: SL must be above entry
        if direction == Direction.LONG:
            # Stop loss should be below entry price
            # Use invalidation if it's below entry, otherwise entry - ATR_buffer
            atrs = detect_support_resistance(candles[:i+1])  # Just to use same function
            # Get ATR for buffer
            from src.indicators import compute_atr
            atr_list = compute_atr(candles[:i+1], 14)
            atr = atr_list[i] if i < len(atr_list) and not math.isnan(atr_list[i]) else entry_price * 0.01

            sl = min(invalidation, entry_price - atr * 0.5)  # Ensure SL below entry
            if sl >= entry_price:
                sl = entry_price - atr * 1.0  # Fallback: 1 ATR below entry
            risk = entry_price - sl
            tp = entry_price + (risk * 2.0)
        else:
            # Stop loss should be above entry price
            from src.indicators import compute_atr
            atr_list = compute_atr(candles[:i+1], 14)
            atr = atr_list[i] if i < len(atr_list) and not math.isnan(atr_list[i]) else entry_price * 0.01

            sl = max(invalidation, entry_price + atr * 0.5)  # Ensure SL above entry
            if sl <= entry_price:
                sl = entry_price + atr * 1.0  # Fallback: 1 ATR above entry
            risk = sl - entry_price
            tp = entry_price - (risk * 2.0)

        if risk <= 0:
            print(f" [{i}] Invalid risk amount: {risk} (entry={entry_price:.2f}, sl={sl:.2f})")
            continue

        rr = abs(tp - entry_price) / risk

        if rr < 2.0:
            print(f" [{i}] Pattern at {pattern_idx} has R:R {rr:.2f} < 2.0, skipping")
            continue

        # Calculate position size (1% risk)
        risk_amount = cash * 0.01
        size = risk_amount / risk
        fee = size * entry_price * 0.001

        if cash >= fee + size * entry_price:
            position = {
                'entry_price': entry_price,
                'size': size,
                'direction': direction,
                'stop_loss': sl,
                'take_profit': tp,
                'entry_index': i,
                'pattern_idx': pattern_idx,
            }
            cash -= (size * entry_price + fee)

            print(f"\n [{i}] ENTERED {direction.value} trade")
            print(f"     Pattern was at index: {pattern_idx}")
            print(f"     Entry: {entry_price:.2f}, SL: {sl:.2f}, TP: {tp:.2f}")
            print(f"     Risk: ${risk:.2f}, R:R: 1:{rr:.2f}")
            print(f"     Size: {size:.4f}, Cash: ${cash:.2f}")

    # Check exit for existing position
    if position:
        sl = position['stop_loss']
        tp = position['take_profit']

        if position['direction'] == Direction.LONG:
            if c.low <= sl:
                pnl = position['size'] * (sl - position['entry_price'])
                cash += pnl
                trades.append({
                    'entry_idx': position['entry_index'],
                    'exit_idx': i,
                    'entry': position['entry_price'],
                    'exit': sl,
                    'pnl': pnl,
                    'reason': 'SL',
                    'pattern_idx': position['pattern_idx']
                })
                print(f" [{i}] EXIT at SL: {sl:.2f}, PnL: ${pnl:.2f}")
                position = None
            elif c.high >= tp:
                pnl = position['size'] * (tp - position['entry_price'])
                cash += pnl
                trades.append({
                    'entry_idx': position['entry_index'],
                    'exit_idx': i,
                    'entry': position['entry_price'],
                    'exit': tp,
                    'pnl': pnl,
                    'reason': 'TP',
                    'pattern_idx': position['pattern_idx']
                })
                print(f" [{i}] EXIT at TP: {tp:.2f}, PnL: ${pnl:.2f}")
                position = None
        else:
            if c.high >= sl:
                pnl = position['size'] * (position['entry_price'] - sl)
                cash += pnl
                trades.append({
                    'entry_idx': position['entry_index'],
                    'exit_idx': i,
                    'entry': position['entry_price'],
                    'exit': sl,
                    'pnl': pnl,
                    'reason': 'SL',
                    'pattern_idx': position['pattern_idx']
                })
                print(f" [{i}] EXIT at SL: {sl:.2f}, PnL: ${pnl:.2f}")
                position = None
            elif c.low <= tp:
                pnl = position['size'] * (position['entry_price'] - tp)
                cash += pnl
                trades.append({
                    'entry_idx': position['entry_index'],
                    'exit_idx': i,
                    'entry': position['entry_price'],
                    'exit': tp,
                    'pnl': pnl,
                    'reason': 'TP',
                    'pattern_idx': position['pattern_idx']
                })
                print(f" [{i}] EXIT at TP: {tp:.2f}, PnL: ${pnl:.2f}")
                position = None

    # Look for new pattern (only if no position and no pending entry)
    if position is None and pending_entry is None:
        pattern_result = detector.detect(
            candles[:i+1],
            PatternType.ENGULFING,
            sr_levels,
            min_confidence=0.3
        )

        if pattern_result:
            # Schedule entry for next candle
            pending_entry = {
                'direction': pattern_result['direction'],
                'invalidation': pattern_result['invalidation_price'],
                'pattern_idx': pattern_result['pattern_index'],
            }

# Close any remaining position
if position:
    last_price = candles[-1].close
    pnl = position['size'] * (last_price - position['entry_price'])
    if position['direction'] == Direction.SHORT:
        pnl = -pnl
    cash += pnl
    trades.append({
        'entry_idx': position['entry_index'],
        'exit_idx': len(candles) - 1,
        'entry': position['entry_price'],
        'exit': last_price,
        'pnl': pnl,
        'reason': 'End',
        'pattern_idx': position['pattern_idx']
    })
    print(f" [END] Closed position at {last_price:.2f}, PnL: ${pnl:.2f}")

# Calculate results
print("\n" + "="*60)
print("BACKTEST RESULTS")
print("="*60)

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
    expectancy = sum(t['pnl'] for t in trades) / len(trades)
    profit_factor = sum(t['pnl'] for t in winning_trades) / abs(sum(t['pnl'] for t in losing_trades)) if losing_trades else float('inf')

    print(f"Win Rate: {win_rate*100:.1f}%")
    print(f"Avg Win: ${avg_win:.2f}")
    print(f"Avg Loss: ${avg_loss:.2f}")
    print(f"Expectancy: ${expectancy:.2f}")
    print(f"Profit Factor: {profit_factor:.2f}")
    print(f"Total Return: {total_return*100:.2f}%")
    print(f"Final Capital: ${cash:.2f}")

print("\nTrade Details:")
for i, t in enumerate(trades, 1):
    print(f"  {i}. Pattern@{t['pattern_idx']}: {t['entry_idx']}->{t['exit_idx']} | {t['reason']} | Entry=${t['entry']:.2f} Exit=${t['exit']:.2f} PnL=${t['pnl']:.2f}")
