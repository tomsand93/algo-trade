"""
Quick test script with database support
Tests a single strategy on one asset/timeframe
"""
import pandas as pd
from backtester import Backtester
from strategies_advanced import STRATEGIES
from database import OHLCVDatabase
import config


def test_single_strategy():
    """Test a single strategy configuration"""

    # Configuration - Edit these to test different combinations
    STRATEGY = "RSI"              # Change to test different strategies
    ASSET = "BTCUSDT"             # BTC, ETH, BNB, etc.
    TIMEFRAME = "1h"              # 1m, 5m, 15m, 1h, 4h, 1d
    RISK = 0.10                   # 10% position size
    INITIAL_CAPITAL = 10000

    print("=" * 70)
    print("SINGLE STRATEGY TEST (Database Mode)")
    print("=" * 70)
    print(f"Strategy: {STRATEGY}")
    print(f"Asset: {ASSET}")
    print(f"Timeframe: {TIMEFRAME}")
    print(f"Risk per Trade: {RISK*100}%")
    print(f"Initial Capital: ${INITIAL_CAPITAL}")
    print("=" * 70)

    # Get strategy function
    if STRATEGY not in STRATEGIES:
        print(f"❌ Strategy '{STRATEGY}' not found!")
        print(f"Available strategies: {list(STRATEGIES.keys())}")
        return

    strategy_func = STRATEGIES[STRATEGY]

    # Load data from database
    db = OHLCVDatabase()

    # Convert to CCXT format
    if ASSET.endswith('USDT'):
        symbol = f"{ASSET[:-4]}/USDT"
    else:
        symbol = ASSET

    print(f"\n📊 Loading data from database for {symbol} {TIMEFRAME}...")
    df = db.load_ohlcv(symbol, TIMEFRAME)

    if df is None or df.empty:
        print(f"❌ No data found in database.")
        print(f"   Run 'python run_v2.py download' first")
        db.close()
        return

    print(f"✓ Loaded {len(df)} candles")
    print(f"  Date range: {df.index[0]} to {df.index[-1]}")

    # Get metadata
    metadata = db.get_metadata(symbol, TIMEFRAME)
    if metadata:
        from datetime import datetime
        last_update = datetime.fromtimestamp(metadata['last_update'] / 1000)
        print(f"  Last updated: {last_update:%Y-%m-%d %H:%M:%S}")

    db.close()

    # Run backtest
    print(f"\n🔬 Running backtest...")
    backtester = Backtester(initial_capital=INITIAL_CAPITAL, commission=0.001)
    result = backtester.run(df, strategy_func, risk_per_trade=RISK)

    # Display results
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    metrics = result['metrics']

    print(f"\n💰 PROFITABILITY")
    print(f"  Initial Capital: ${INITIAL_CAPITAL:,.2f}")
    print(f"  Final Equity: ${result['final_equity']:,.2f}")
    print(f"  Total Return: ${metrics['total_return']:,.2f}")
    print(f"  Total Return %: {metrics['total_return_pct']:.2f}%")

    print(f"\n📊 TRADING ACTIVITY")
    print(f"  Total Trades: {metrics['num_trades']}")
    print(f"  Win Rate: {metrics['win_rate']:.1f}%")
    print(f"  Profit Factor: {metrics['profit_factor']:.2f}")
    print(f"  Avg Win: ${metrics['avg_win']:.2f}")
    print(f"  Avg Loss: ${metrics['avg_loss']:.2f}")

    print(f"\n📈 RISK METRICS")
    print(f"  Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
    print(f"  Sortino Ratio: {metrics['sortino_ratio']:.2f}")
    print(f"  Max Drawdown: {metrics['max_drawdown_pct']:.2f}%")

    print(f"\n💸 COSTS")
    print(f"  Total Commission: ${metrics['total_commission']:.2f}")

    # Show some trades
    trades = result['trades']
    if trades:
        print(f"\n📝 LAST 5 TRADES")
        print("-" * 70)
        for trade in trades[-5:]:
            trade_type = trade['type']
            timestamp = trade['timestamp']
            price = trade['price']
            pnl = trade.get('pnl', 0)

            if trade_type == 'BUY':
                print(f"  {timestamp} | BUY @ ${price:,.2f}")
            else:
                pnl_str = f"${pnl:,.2f}" if pnl > 0 else f"-${abs(pnl):,.2f}"
                emoji = "✅" if pnl > 0 else "❌"
                print(f"  {timestamp} | SELL @ ${price:,.2f} | P&L: {pnl_str} {emoji}")

    print("\n" + "=" * 70)

    # Performance rating
    sharpe = metrics['sharpe_ratio']
    return_pct = metrics['total_return_pct']

    print("\n🎯 PERFORMANCE RATING")
    if return_pct > 50 and sharpe > 2:
        print("  ⭐⭐⭐⭐⭐ EXCELLENT - High returns with good risk management")
    elif return_pct > 20 and sharpe > 1:
        print("  ⭐⭐⭐⭐ GOOD - Solid returns with acceptable risk")
    elif return_pct > 0 and sharpe > 0.5:
        print("  ⭐⭐⭐ DECENT - Profitable but could be better")
    elif return_pct > 0:
        print("  ⭐⭐ MARGINAL - Profitable but high risk")
    else:
        print("  ⭐ POOR - Losing strategy")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    test_single_strategy()
