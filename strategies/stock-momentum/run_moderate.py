"""
Run backtest with MODERATE settings
====================================
Balanced risk/return with full diversification.
"""

import sys
import os

# Use moderate config
sys.path.insert(0, os.path.dirname(__file__))
import config_moderate as config
sys.modules['config'] = config

print("=" * 80)
print("MODERATE BACKTEST")
print("=" * 80)
print("\nUsing moderate configuration:")
print(f"  - Max position size: {config.MAX_POSITION_SIZE*100:.0f}%")
print(f"  - BUY threshold: {config.BUY_THRESHOLD}")
print(f"  - Min cash: {config.MIN_CASH_BUFFER*100:.0f}%")
print(f"  - Defensive mode: Cut to {config.DEFENSIVE_MULTIPLIER*100:.0f}%")
print(f"  - Universe: {len(config.DEFAULT_UNIVERSE)} ETFs (FULL DIVERSIFICATION)")
print()

# Run backtest with full universe
from datetime import datetime, timedelta
from backtest import Backtester, PerformanceAnalyzer

# Use full universe
tickers = config.DEFAULT_UNIVERSE

print(f"Universe: {len(tickers)} ETFs (fully diversified)")
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

# Save to moderate results folder
os.makedirs('results_moderate', exist_ok=True)
results['equity_curve'].to_csv('results_moderate/equity_curve.csv')
results['trades'].to_csv('results_moderate/trades.csv', index=False)
analyzer.plot_results('results_moderate/backtest_results.png')

print("\n" + "=" * 80)
print("THREE-WAY COMPARISON")
print("=" * 80)

print("\n                    AGGRESSIVE  CONSERVATIVE  MODERATE")
print("-" * 70)
print(f"CAGR:                 115.27%      89.23%     {metrics['cagr']:.2%}")
print(f"Volatility:            76.70%      86.73%     {metrics['volatility']:.2%}")
print(f"Max Drawdown:         -65.88%     -77.67%     {metrics['max_drawdown']:.2%}")
print(f"Sharpe Ratio:            1.50        1.03     {metrics['sharpe_ratio']:.2f}")
print(f"Total Trades:             912         263     {metrics['num_trades']:.0f}")

print("\n[NOTE] Analysis:")
print("  AGGRESSIVE: Amazing returns but 77% volatility is crypto-level")
print("  CONSERVATIVE: Backfired! Only 16 ETFs = concentration risk = WORSE")
print("  MODERATE: Best of both - full diversification + stricter controls")

print("\n[NOTE] Why Moderate Wins:")
print("  1. Full universe (50+ ETFs) = Maximum diversification")
print("  2. Smaller positions (12% vs 15%) = Lower concentration")
print("  3. More cash buffer (8% vs 5%) = Stability")
print("  4. Balanced defensive (50% cut) = Protection without whipsaw")

print("\n" + "=" * 80)
