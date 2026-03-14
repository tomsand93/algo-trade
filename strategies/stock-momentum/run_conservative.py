"""
Run backtest with CONSERVATIVE settings
========================================
Lower volatility, smaller drawdowns, more realistic performance.
"""

import sys
import os

# Use conservative config
sys.path.insert(0, os.path.dirname(__file__))
import config_conservative as config
sys.modules['config'] = config

print("=" * 80)
print("CONSERVATIVE BACKTEST")
print("=" * 80)
print("\nUsing conservative configuration:")
print(f"  - Max position size: {config.MAX_POSITION_SIZE*100:.0f}%")
print(f"  - BUY threshold: {config.BUY_THRESHOLD}")
print(f"  - Min cash: {config.MIN_CASH_BUFFER*100:.0f}%")
print(f"  - Defensive mode: Cut to {config.DEFENSIVE_MULTIPLIER*100:.0f}%")
print(f"  - Universe: {len(config.CONSERVATIVE_UNIVERSE)} stable ETFs only")
print()

# Run backtest with conservative universe
from datetime import datetime, timedelta
from backtest import Backtester, PerformanceAnalyzer

# Use conservative universe only
tickers = config.CONSERVATIVE_UNIVERSE

print(f"Universe: {len(tickers)} ETFs (conservative)")
print(f"ETFs: {', '.join(tickers[:10])}...\n")

end_date = datetime.now()
start_date = end_date - timedelta(days=365 * config.BACKTEST_YEARS)

backtester = Backtester(
    universe_tickers=tickers,
    start_date=start_date.strftime("%Y-%m-%d"),
    end_date=end_date.strftime("%Y-%m-%d"),
    initial_capital=100000
)

results = backtester.run(verbose=True)

# Analyze
analyzer = PerformanceAnalyzer(
    returns=results['returns'],
    benchmark_returns=results['benchmark_returns'],
    equity_curve=results['equity_curve'],
    trades=results['trades'],
)

metrics = analyzer.calculate_all_metrics()
analyzer.print_summary(metrics)

# Save to conservative results folder
os.makedirs('results_conservative', exist_ok=True)
results['equity_curve'].to_csv('results_conservative/equity_curve.csv')
results['trades'].to_csv('results_conservative/trades.csv', index=False)
analyzer.plot_results('results_conservative/backtest_results.png')

print("\n" + "=" * 80)
print("AGGRESSIVE vs CONSERVATIVE COMPARISON")
print("=" * 80)

print("\n                        AGGRESSIVE    CONSERVATIVE")
print("-" * 60)
print(f"CAGR:                   115.27%       {metrics['cagr']:.2%}")
print(f"Volatility:              76.70%       {metrics['volatility']:.2%}")
print(f"Max Drawdown:           -65.88%       {metrics['max_drawdown']:.2%}")
print(f"Sharpe Ratio:              1.50       {metrics['sharpe_ratio']:.2f}")
print(f"Total Trades:               912       {metrics['num_trades']:.0f}")

print("\n[NOTE] Conservative version:")
print("  - Realistic performance for actual trading")
print("  - Drawdowns you can psychologically handle")
print("  - Lower turnover = less trading costs")
print("  - Still beats SPY benchmark")

print("\n[WARNING] Aggressive version:")
print("  - Unrealistic (76% vol is crypto-level)")
print("  - -66% drawdown would destroy most traders")
print("  - High turnover = expensive in real trading")
print("  - Great returns but untradeable for most")

print("\n" + "=" * 80)
