"""
Quick Test Script

Test a single strategy on one asset/timeframe
Useful for debugging and parameter tuning
"""
from database import OHLCVDatabase
from backtest_engine import BacktestEngine
from strategies import STRATEGIES
import config


def test_strategy():
    """Test single strategy configuration"""

    # ===== CONFIGURATION =====
    # Edit these to test different setups
    STRATEGY = "RSI"              # RSI, MACD, BOLLINGER_BANDS, etc.
    ASSET = "BTCUSDT"             # BTCUSDT, ETHUSDT, BNBUSDT, etc.
    TIMEFRAME = "1h"              # 5m, 15m, 1h, 4h, 1d
    RISK = 0.10                   # 10% position size
    INITIAL_CAPITAL = 10000
    # ========================

    print("=" * 70)
    print("STRATEGY TEST")
    print("=" * 70)
    print(f"Strategy: {STRATEGY}")
    print(f"Asset: {ASSET}")
    print(f"Timeframe: {TIMEFRAME}")
    print(f"Risk: {RISK*100}%")
    print(f"Capital: ${INITIAL_CAPITAL:,}")
    print("=" * 70)

    # Validate strategy
    if STRATEGY not in STRATEGIES:
        print(f"\n❌ Strategy '{STRATEGY}' not found!")
        print(f"Available: {list(STRATEGIES.keys())}")
        return

    strategy_func = STRATEGIES[STRATEGY]

    # Load data from database
    db = OHLCVDatabase()

    # Convert to CCXT format
    if ASSET.endswith('USDT'):
        symbol = f"{ASSET[:-4]}/USDT"
    else:
        symbol = ASSET

    print(f"\n📊 Loading data: {symbol} {TIMEFRAME}")
    df = db.load_ohlcv(symbol, TIMEFRAME)

    if df is None or df.empty:
        print(f"❌ No data found!")
        print(f"Run: python run.py download")
        db.close()
        return

    print(f"✓ Loaded {len(df)} candles")
    print(f"  Period: {df.index[0]:%Y-%m-%d} to {df.index[-1]:%Y-%m-%d}")

    # Show metadata
    metadata = db.get_metadata(symbol, TIMEFRAME)
    if metadata:
        from datetime import datetime
        last_update = datetime.fromtimestamp(metadata['last_update'] / 1000)
        print(f"  Updated: {last_update:%Y-%m-%d %H:%M:%S}")

    db.close()

    # Run backtest
    print(f"\n🔬 Running backtest...")
    engine = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    result = engine.run(df, strategy_func, risk_per_trade=RISK)

    # Display results
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    m = result['metrics']

    print(f"\n💰 PROFITABILITY")
    print(f"  Initial Capital:    ${INITIAL_CAPITAL:>12,.2f}")
    print(f"  Final Equity:       ${result['final_equity']:>12,.2f}")
    print(f"  Total Return:       ${m['total_return']:>12,.2f}")
    print(f"  Total Return %:     {m['total_return_pct']:>12.2f}%")

    print(f"\n📊 TRADING")
    print(f"  Total Trades:       {m['num_trades']:>12}")
    print(f"  Winning Trades:     {m['num_winning_trades']:>12}")
    print(f"  Losing Trades:      {m['num_losing_trades']:>12}")
    print(f"  Win Rate:           {m['win_rate']:>12.1f}%")
    print(f"  Profit Factor:      {m['profit_factor']:>12.2f}")
    print(f"  Avg Win:            ${m['avg_win']:>12.2f}")
    print(f"  Avg Loss:           ${m['avg_loss']:>12.2f}")
    print(f"  Best Trade:         ${m['best_trade']:>12.2f}")
    print(f"  Worst Trade:        ${m['worst_trade']:>12.2f}")

    print(f"\n📈 RISK METRICS")
    print(f"  Sharpe Ratio:       {m['sharpe_ratio']:>12.2f}")
    print(f"  Sortino Ratio:      {m['sortino_ratio']:>12.2f}")
    print(f"  Max Drawdown:       {m['max_drawdown_pct']:>12.2f}%")

    print(f"\n💸 COSTS")
    print(f"  Total Commission:   ${m['total_commission']:>12.2f}")

    # Show recent trades
    trades = result['trades']
    if trades:
        print(f"\n📝 RECENT TRADES")
        print("-" * 70)
        for trade in trades[-5:]:
            ts = trade['timestamp']
            typ = trade['type']
            price = trade['price']
            pnl = trade.get('pnl', 0)

            if typ == 'BUY':
                print(f"  {ts} | BUY  @ ${price:>10,.2f}")
            else:
                sign = "+" if pnl > 0 else ""
                emoji = "✅" if pnl > 0 else "❌"
                print(f"  {ts} | SELL @ ${price:>10,.2f} | P&L: {sign}${pnl:>8,.2f} {emoji}")

    print("\n" + "=" * 70)

    # Rating
    print("\n🎯 PERFORMANCE RATING")
    sharpe = m['sharpe_ratio']
    ret = m['total_return_pct']

    if ret > 50 and sharpe > 2:
        print("  ⭐⭐⭐⭐⭐ EXCELLENT - High returns, low risk")
    elif ret > 20 and sharpe > 1:
        print("  ⭐⭐⭐⭐ GOOD - Solid returns, acceptable risk")
    elif ret > 0 and sharpe > 0.5:
        print("  ⭐⭐⭐ DECENT - Profitable but needs improvement")
    elif ret > 0:
        print("  ⭐⭐ MARGINAL - Profitable but risky")
    else:
        print("  ⭐ POOR - Losing strategy")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    test_strategy()
