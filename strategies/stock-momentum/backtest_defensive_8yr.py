"""
OLD DEFENSIVE STRATEGY - 8-YEAR BACKTEST
========================================
Run the original defensive strategy on 8-year period for comparison
"""

import sys
import os
sys.path.insert(0, r"C:\Users\Tom1\Desktop\TRADING\production\stock_momentum")
import config
from backtest import Backtester, PerformanceAnalyzer

print("\n" + "="*80)
print("OLD DEFENSIVE STRATEGY - 8-YEAR BACKTEST")
print("="*80)
print("\nStrategy:")
print("  - Cut positions 50% when SPY < 200-day MA (defensive mode)")
print("  - Standard rebalancing logic")
print("  - 8% cash buffer\n")

# Run 8-year backtest
backtester = Backtester(
    universe_tickers=config.DEFAULT_UNIVERSE,
    start_date='2016-01-01',
    end_date='2023-12-31',
    initial_capital=100000
)

results = backtester.run(verbose=True)

# Analyze performance
analyzer = PerformanceAnalyzer(
    returns=results['returns'],
    benchmark_returns=results['benchmark_returns'],
    equity_curve=results['equity_curve'],
    trades=results['trades'],
)

metrics = analyzer.calculate_all_metrics()

# Print results
print("\n" + "="*80)
print("PERFORMANCE METRICS (Defensive Strategy: 2016-2023)")
print("="*80)
print(f"\n{'Metric':<25} {'Defensive':>15}")
print("-" * 80)
print(f"{'Total Return':<25} {metrics['total_return']:>14.2%}")
print(f"{'CAGR':<25} {metrics['cagr']:>14.2%}")
print(f"{'Volatility':<25} {metrics['volatility']:>14.2%}")
print(f"{'Sharpe Ratio':<25} {metrics['sharpe_ratio']:>14.2f}")
print(f"{'Sortino Ratio':<25} {metrics['sortino_ratio']:>14.2f}")
print(f"{'Max Drawdown':<25} {metrics['max_drawdown']:>14.2%}")
print(f"{'Win Rate':<25} {metrics.get('win_rate', 0):>14.2%}")
print(f"{'Total Trades':<25} {metrics.get('num_trades', 0):>15.0f}")
print("="*80)
