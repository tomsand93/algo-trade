"""
Multi-Period Backtesting
=========================
Test strategy across different market conditions (2016-2026).
"""

import sys
import os
from datetime import datetime, timedelta
import pandas as pd

# Use moderate config
sys.path.insert(0, os.path.dirname(__file__))
import config_moderate as config
sys.modules['config'] = config

from backtest import Backtester, PerformanceAnalyzer

print("=" * 80)
print("MULTI-PERIOD BACKTEST ANALYSIS")
print("=" * 80)
print("\nTesting MODERATE strategy across different market conditions")
print(f"Universe: {len(config.DEFAULT_UNIVERSE)} ETFs")
print(f"Config: {config.MAX_POSITION_SIZE*100:.0f}% max position, {config.BUY_THRESHOLD} threshold\n")

# Define periods (2-year chunks)
periods = [
    ("2016-01-01", "2017-12-31", "2016-2017: Bull Market"),
    ("2018-01-01", "2019-12-31", "2018-2019: Late Bull + Correction"),
    ("2020-01-01", "2021-12-31", "2020-2021: COVID Crash + Recovery"),
    ("2022-01-01", "2023-12-31", "2022-2023: Bear Market + Rebound"),
    ("2024-01-01", "2025-12-31", "2024-2025: Recent Bull Market"),
]

# Storage for results
all_results = []

# Run backtest for each period
for start_date, end_date, description in periods:
    print("\n" + "=" * 80)
    print(f"PERIOD: {description}")
    print("=" * 80)
    print(f"Dates: {start_date} to {end_date}\n")

    try:
        # Run backtest
        backtester = Backtester(
            universe_tickers=config.DEFAULT_UNIVERSE,
            start_date=start_date,
            end_date=end_date,
            initial_capital=100000
        )

        results = backtester.run(verbose=False)

        # Analyze
        analyzer = PerformanceAnalyzer(
            returns=results['returns'],
            benchmark_returns=results['benchmark_returns'],
            equity_curve=results['equity_curve'],
            trades=results['trades'],
        )

        metrics = analyzer.calculate_all_metrics()

        # Print summary
        print(f"\n[RESULTS]")
        print(f"   CAGR:            {metrics['cagr']:>8.2%}")
        print(f"   Volatility:      {metrics['volatility']:>8.2%}")
        print(f"   Max Drawdown:    {metrics['max_drawdown']:>8.2%}")
        print(f"   Sharpe Ratio:    {metrics['sharpe_ratio']:>8.2f}")
        print(f"   Total Trades:    {metrics['num_trades']:>8.0f}")
        print(f"   Win Rate:        {metrics['win_rate']:>8.2%}")
        print(f"   vs SPY:          {metrics['alpha']:>8.2%}")

        # Store results
        all_results.append({
            'Period': description,
            'Start': start_date,
            'End': end_date,
            'CAGR': metrics['cagr'],
            'Volatility': metrics['volatility'],
            'Max_DD': metrics['max_drawdown'],
            'Sharpe': metrics['sharpe_ratio'],
            'Trades': metrics['num_trades'],
            'Win_Rate': metrics['win_rate'],
            'Alpha': metrics['alpha'],
            'SPY_CAGR': metrics['benchmark_cagr'],
        })

        # Save results for this period
        period_name = start_date[:4] + "_" + end_date[:4]
        os.makedirs(f'results_periods/{period_name}', exist_ok=True)
        results['equity_curve'].to_csv(f'results_periods/{period_name}/equity_curve.csv')
        results['trades'].to_csv(f'results_periods/{period_name}/trades.csv', index=False)

    except Exception as e:
        print(f"\n[ERROR] Failed to run backtest: {e}")
        import traceback
        traceback.print_exc()

# Create comparison table
print("\n\n" + "=" * 80)
print("COMPARISON ACROSS ALL PERIODS")
print("=" * 80)

df_results = pd.DataFrame(all_results)

print("\n[TABLE]")
print(df_results.to_string(index=False))

# Summary statistics
print("\n\n" + "=" * 80)
print("SUMMARY STATISTICS")
print("=" * 80)

print(f"\n[AVERAGE PERFORMANCE]")
print(f"   Avg CAGR:        {df_results['CAGR'].mean():>8.2%}")
print(f"   Avg Volatility:  {df_results['Volatility'].mean():>8.2%}")
print(f"   Avg Max DD:      {df_results['Max_DD'].mean():>8.2%}")
print(f"   Avg Sharpe:      {df_results['Sharpe'].mean():>8.2f}")
print(f"   Avg Alpha:       {df_results['Alpha'].mean():>8.2%}")

print(f"\n[CONSISTENCY]")
print(f"   Best Period:     {df_results.loc[df_results['CAGR'].idxmax(), 'Period']}")
print(f"   Best CAGR:       {df_results['CAGR'].max():>8.2%}")
print(f"   Worst Period:    {df_results.loc[df_results['CAGR'].idxmin(), 'Period']}")
print(f"   Worst CAGR:      {df_results['CAGR'].min():>8.2%}")
print(f"   Win Periods:     {(df_results['CAGR'] > 0).sum()}/{len(df_results)}")

print(f"\n[RISK ANALYSIS]")
print(f"   Lowest Vol:      {df_results['Volatility'].min():>8.2%} ({df_results.loc[df_results['Volatility'].idxmin(), 'Period']})")
print(f"   Highest Vol:     {df_results['Volatility'].max():>8.2%} ({df_results.loc[df_results['Volatility'].idxmax(), 'Period']})")
print(f"   Best Sharpe:     {df_results['Sharpe'].max():>8.2f} ({df_results.loc[df_results['Sharpe'].idxmax(), 'Period']})")
print(f"   Worst Sharpe:    {df_results['Sharpe'].min():>8.2f} ({df_results.loc[df_results['Sharpe'].idxmin(), 'Period']})")

print(f"\n[vs BENCHMARK]")
print(f"   Periods beating SPY: {(df_results['Alpha'] > 0).sum()}/{len(df_results)}")
print(f"   Avg outperformance:  {df_results['Alpha'].mean():>8.2%}")

# Save summary
df_results.to_csv('results_periods/summary.csv', index=False)

print("\n\n" + "=" * 80)
print("KEY INSIGHTS")
print("=" * 80)

# Identify market conditions
if len(df_results) > 0:
    best_period = df_results.loc[df_results['CAGR'].idxmax()]
    worst_period = df_results.loc[df_results['CAGR'].idxmin()]

    print(f"\n[BEST PERIOD] {best_period['Period']}")
    print(f"   Strategy: {best_period['CAGR']:.2%} CAGR")
    print(f"   SPY:      {best_period['SPY_CAGR']:.2%} CAGR")
    print(f"   Alpha:    {best_period['Alpha']:.2%}")

    print(f"\n[WORST PERIOD] {worst_period['Period']}")
    print(f"   Strategy: {worst_period['CAGR']:.2%} CAGR")
    print(f"   SPY:      {worst_period['SPY_CAGR']:.2%} CAGR")
    print(f"   Alpha:    {worst_period['Alpha']:.2%}")

    print("\n[INTERPRETATION]")
    if df_results['CAGR'].mean() > 0.20:
        print("   Strong performance across periods")
    elif df_results['CAGR'].mean() > 0.10:
        print("   Moderate performance across periods")
    else:
        print("   Weak performance across periods")

    if (df_results['Alpha'] > 0).sum() / len(df_results) > 0.75:
        print("   Consistently beats benchmark")
    elif (df_results['Alpha'] > 0).sum() / len(df_results) > 0.50:
        print("   Usually beats benchmark")
    else:
        print("   Inconsistent vs benchmark")

    if df_results['Volatility'].mean() > 0.50:
        print("   [WARNING] Very high volatility strategy")
    elif df_results['Volatility'].mean() > 0.30:
        print("   Moderate to high volatility")
    else:
        print("   Normal volatility levels")

print("\n\n[FILES SAVED]")
print("   results_periods/summary.csv")
for period_name in ['2016_2017', '2018_2019', '2020_2021', '2022_2023', '2024_2025']:
    if os.path.exists(f'results_periods/{period_name}'):
        print(f"   results_periods/{period_name}/")

print("\n" + "=" * 80)
