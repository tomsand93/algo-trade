"""
Fixed Backtest System with Proper Risk Management

Fixes:
1. Fixed fractional position sizing (1% of capital per trade)
2. Trend filter (only trade WITH the 50-EMA trend)
3. Volume confirmation (only trade when volume is above average)
4. Stricter pattern validation
5. Proper SL/TP calculations
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import Candle, PatternType, Direction
from src.patterns import PatternDetector
from src.indicators import detect_support_resistance, compute_atr
import math
import csv

# Configuration
CAPITAL_PER_TRADE_PCT = 0.01  # 1% of capital per trade (position value)
MIN_VOLUME_PERCENTILE = 50    # Only trade when volume > 50th percentile
TREND_EMA_PERIOD = 50         # EMA period for trend filter


def load_candles(filepath):
    """Load candles from CSV."""
    candles = []
    with open(filepath, 'r') as f:
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
    return candles


def compute_ema(prices, period):
    """Compute Exponential Moving Average."""
    multiplier = 2 / (period + 1)
    ema = [float('nan')] * len(prices)

    if len(prices) < period:
        return ema

    # Initialize with SMA
    ema[period - 1] = sum(prices[:period]) / period

    for i in range(period, len(prices)):
        ema[i] = (prices[i] - ema[i-1]) * multiplier + ema[i-1]

    return ema


def get_trend(candles, index, ema_period=50):
    """
    Get trend direction at index.
    Returns: 1 (uptrend), -1 (downtrend), 0 (neutral)
    """
    if index < ema_period:
        return 0

    closes = [c.close for c in candles[:index+1]]
    ema = compute_ema(closes, ema_period)

    if ema[index] is None or ema[index-5] is None:
        return 0

    # Price above EMA and EMA rising = uptrend
    if closes[index] > ema[index] and ema[index] > ema[index-5]:
        return 1
    # Price below EMA and EMA falling = downtrend
    elif closes[index] < ema[index] and ema[index] < ema[index-5]:
        return -1
    else:
        return 0


def get_volume_percentile(candles, index, period=20):
    """Get volume percentile (0-100) for candle at index."""
    if index < period:
        return 50

    volumes = [c.volume for c in candles[index-period+1:index+1]]
    current = candles[index].volume

    higher = sum(1 for v in volumes if v < current)
    return (higher / len(volumes)) * 100


def run_fixed_backtest(candles, pattern_type=PatternType.ENGULFING):
    """Run backtest with fixed position sizing."""

    print(f"Loaded {len(candles)} candles")
    print(f"Date range: {candles[0].datetime} to {candles[-1].datetime}")
    print(f"Price range: ${min(c.low for c in candles):,.2f} - ${max(c.high for c in candles):,.2f}")

    # Pre-compute indicators
    print("\nPre-computing indicators...")
    atrs = compute_atr(candles, 14)
    sr_levels = detect_support_resistance(candles)
    print(f"  ATR computed: {len(atrs)} values")
    print(f"  S/R levels: {len(sr_levels)} levels")

    # Initialize components
    detector = PatternDetector()

    # Backtest state
    cash = 100000
    position = None
    trades = []
    equity_curve = [cash]
    patterns_found = 0
    patterns_failed_trend = 0
    patterns_failed_volume = 0
    patterns_failed_rr = 0

    print("\n" + "="*60)
    print("BACKTEST EXECUTION")
    print("="*60)

    # Start from where we have enough data
    start_idx = max(100, TREND_EMA_PERIOD + 20)

    for i in range(start_idx, len(candles)):
        c = candles[i]

        # Check exit for existing position
        if position:
            sl = position['stop_loss']
            tp = position['take_profit']

            if position['direction'] == Direction.LONG:
                if c.low <= sl:
                    pnl = position['size'] * (sl - position['entry_price']) - position['exit_fee']
                    cash += pnl
                    trades.append({
                        'entry_idx': position['entry_index'],
                        'exit_idx': i,
                        'entry': position['entry_price'],
                        'exit': sl,
                        'pnl': pnl,
                        'reason': 'SL',
                        'bars': i - position['entry_index']
                    })
                    print(f" [{i}] LONG Exit SL: ${sl:,.2f} | PnL: ${pnl:,.2f}")
                    position = None
                elif c.high >= tp:
                    pnl = position['size'] * (tp - position['entry_price']) - position['exit_fee']
                    cash += pnl
                    trades.append({
                        'entry_idx': position['entry_index'],
                        'exit_idx': i,
                        'entry': position['entry_price'],
                        'exit': tp,
                        'pnl': pnl,
                        'reason': 'TP',
                        'bars': i - position['entry_index']
                    })
                    print(f" [{i}] LONG Exit TP: ${tp:,.2f} | PnL: ${pnl:,.2f}")
                    position = None
            else:  # SHORT
                if c.high >= sl:
                    pnl = position['size'] * (position['entry_price'] - sl) - position['exit_fee']
                    cash += pnl
                    trades.append({
                        'entry_idx': position['entry_index'],
                        'exit_idx': i,
                        'entry': position['entry_price'],
                        'exit': sl,
                        'pnl': pnl,
                        'reason': 'SL',
                        'bars': i - position['entry_index']
                    })
                    print(f" [{i}] SHORT Exit SL: ${sl:,.2f} | PnL: ${pnl:,.2f}")
                    position = None
                elif c.low <= tp:
                    pnl = position['size'] * (position['entry_price'] - tp) - position['exit_fee']
                    cash += pnl
                    trades.append({
                        'entry_idx': position['entry_index'],
                        'exit_idx': i,
                        'entry': position['entry_price'],
                        'exit': tp,
                        'pnl': pnl,
                        'reason': 'TP',
                        'bars': i - position['entry_index']
                    })
                    print(f" [{i}] SHORT Exit TP: ${tp:,.2f} | PnL: ${pnl:,.2f}")
                    position = None

        equity_curve.append(cash)

        # Look for new pattern
        if position is None:
            result = detector.detect(
                candles[:i+1],
                pattern_type,
                sr_levels,
                min_confidence=0.6  # Higher threshold
            )

            if result:
                patterns_found += 1
                pattern_idx = result['pattern_index']
                direction = result['direction']
                confidence = result['confidence']

                # FILTER 1: Trend alignment
                trend = get_trend(candles, i, TREND_EMA_PERIOD)

                # For LONG: need uptrend, for SHORT: need downtrend
                if direction == Direction.LONG and trend != 1:
                    patterns_failed_trend += 1
                    continue
                if direction == Direction.SHORT and trend != -1:
                    patterns_failed_trend += 1
                    continue

                # FILTER 2: Volume confirmation
                vol_pct = get_volume_percentile(candles, i, 20)
                if vol_pct < MIN_VOLUME_PERCENTILE:
                    patterns_failed_volume += 1
                    continue

                # Calculate entry and SL/TP
                entry_price = candles[i+1].open if i+1 < len(candles) else c.close
                atr_val = atrs[i] if not math.isnan(atrs[i]) else entry_price * 0.01

                if direction == Direction.LONG:
                    sl = result['invalidation_price']
                    # Ensure SL is below entry
                    if sl >= entry_price:
                        sl = entry_price - atr_val * 1.5
                    risk = entry_price - sl
                    tp = entry_price + (risk * 2.0)
                else:
                    sl = result['invalidation_price']
                    # Ensure SL is above entry
                    if sl <= entry_price:
                        sl = entry_price + atr_val * 1.5
                    risk = sl - entry_price
                    tp = entry_price - (risk * 2.0)

                if risk <= 0:
                    continue

                rr = abs(tp - entry_price) / risk

                # FILTER 3: Minimum R:R
                if rr < 2.0:
                    patterns_failed_rr += 1
                    continue

                # FIXED POSITION SIZING: Use fixed % of capital
                position_value = cash * CAPITAL_PER_TRADE_PCT
                size = position_value / entry_price

                # Entry fee
                entry_fee = position_value * 0.001

                # Check we have enough cash
                if cash < position_value + entry_fee:
                    continue

                # Enter position
                # Exit fee (same as entry for simplicity)
                exit_fee = position_value * 0.001

                position = {
                    'entry_price': entry_price,
                    'size': size,
                    'direction': direction,
                    'stop_loss': sl,
                    'take_profit': tp,
                    'entry_index': i+1,
                    'entry_fee': entry_fee,
                    'exit_fee': exit_fee,
                }
                cash -= (position_value + entry_fee)

                trend_str = "UPTREND" if trend == 1 else "DOWNTREND" if trend == -1 else "NEUTRAL"

                print(f"\n [{i}] ENTER {direction.value} | {trend_str} | Vol: {vol_pct:.0f}th pct")
                print(f"     Pattern idx: {pattern_idx} | Confidence: {confidence:.2f}")
                print(f"     Entry: ${entry_price:,.2f}")
                print(f"     SL: ${sl:,.2f} | TP: ${tp:,.2f}")
                print(f"     Risk: ${risk:,.2f} | R:R: 1:{rr:.2f}")
                print(f"     Size: {size:.6f} BTC (${position_value:,.2f}) | Cash: ${cash:,.2f}")

    # Close remaining position
    if position:
        last_price = candles[-1].close
        pnl = position['size'] * (last_price - position['entry_price']) - position['exit_fee']
        if position['direction'] == Direction.SHORT:
            pnl = position['size'] * (position['entry_price'] - last_price) - position['exit_fee']
        cash += pnl
        trades.append({
            'entry_idx': position['entry_index'],
            'exit_idx': len(candles) - 1,
            'entry': position['entry_price'],
            'exit': last_price,
            'pnl': pnl,
            'reason': 'End',
            'bars': len(candles) - position['entry_index']
        })
        print(f" [END] Close at ${last_price:,.2f} | PnL: ${pnl:,.2f}")

    # Calculate results
    print("\n" + "="*60)
    print("BACKTEST RESULTS")
    print("="*60)

    print(f"\nPattern Detection:")
    print(f"  Patterns found: {patterns_found}")
    print(f"  Failed (trend): {patterns_failed_trend}")
    print(f"  Failed (volume): {patterns_failed_volume}")
    print(f"  Failed (R:R): {patterns_failed_rr}")

    winning_trades = [t for t in trades if t['pnl'] > 0]
    losing_trades = [t for t in trades if t['pnl'] <= 0]

    print(f"\nTrade Statistics:")
    print(f"  Total Trades: {len(trades)}")
    print(f"  Winning Trades: {len(winning_trades)}")
    print(f"  Losing Trades: {len(losing_trades)}")

    if trades:
        win_rate = len(winning_trades) / len(trades)
        avg_win = sum(t['pnl'] for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(t['pnl'] for t in losing_trades) / len(losing_trades) if losing_trades else 0
        total_return = (cash - 100000) / 100000
        expectancy = sum(t['pnl'] for t in trades) / len(trades)

        gross_profit = sum(t['pnl'] for t in winning_trades)
        gross_loss = abs(sum(t['pnl'] for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Max drawdown
        peak = equity_curve[0]
        max_dd = 0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        print(f"\nPerformance:")
        print(f"  Win Rate: {win_rate*100:.1f}%")
        print(f"  Avg Win: ${avg_win:,.2f}")
        print(f"  Avg Loss: ${avg_loss:,.2f}")
        print(f"  Expectancy: ${expectancy:,.2f} per trade")
        print(f"  Profit Factor: {profit_factor:.2f}")
        print(f"  Total Return: {total_return*100:.2f}%")
        print(f"  Max Drawdown: {max_dd*100:.2f}%")
        print(f"  Final Capital: ${cash:,.2f}")

        avg_bars = sum(t['bars'] for t in trades) / len(trades)
        print(f"  Avg Trade Duration: {avg_bars:.1f} bars")

    print("\nTrade Details:")
    print("  #  | Entry Date | Exit Date | Entry $ | Exit $ | PnL $ | Reason | Bars")
    print("-" * 80)
    for i, t in enumerate(trades, 1):
        entry_date = candles[t['entry_idx']].datetime.strftime('%Y-%m-%d')
        exit_date = candles[t['exit_idx']].datetime.strftime('%Y-%m-%d')
        pnl_str = f"${t['pnl']:,.2f}"
        if t['pnl'] > 0:
            pnl_str = "+" + pnl_str
        print(f"  {i:2d} | {entry_date} | {exit_date} | ${t['entry']:>9,.2f} | ${t['exit']:>9,.2f} | {pnl_str:>10} | {t['reason']:6} | {t['bars']:4}")

    return {
        'total_trades': len(trades),
        'win_rate': win_rate if trades else 0,
        'total_return': total_return if trades else 0,
        'max_drawdown': max_dd if trades else 0,
        'final_capital': cash,
        'expectancy': expectancy if trades else 0,
        'profit_factor': profit_factor if trades else 0,
    }


if __name__ == '__main__':
    # Try to load real data, fall back to test data
    data_file = 'data/btc_usdt_1h_real.csv'

    try:
        candles = load_candles(data_file)
        print(f"Using REAL data from {data_file}")
    except FileNotFoundError:
        # Fall back to test data
        data_file = 'data/obvious_engulfing.csv'
        candles = load_candles(data_file)
        print(f"Using TEST data from {data_file}")

    results = run_fixed_backtest(candles)

    print("\n" + "="*60)
    if results['total_trades'] > 0:
        if results['total_return'] > 0:
            print("[OK] System shows POSITIVE return!")
        else:
            print("[X] System shows NEGATIVE return - needs optimization")
    else:
        print("[!] No trades executed - filters may be too strict")
    print("="*60)
