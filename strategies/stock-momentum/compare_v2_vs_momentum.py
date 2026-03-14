"""
AGGRESSIVE V2 vs MOMENTUM STRATEGY COMPARISON
==============================================
Compare both strategies on the same universe and time periods.
"""

import pandas as pd
import numpy as np
from datetime import datetime
import config
from backtest_aggressive_v2 import AggressiveBacktesterV2
from backtest import Backtester, PerformanceAnalyzer

def run_comparison():
    """Run both strategies and compare results"""

    # Use the merged universe (Top 500 + user stocks)
    universe = config.TOP_500_COMMON_STOCKS

    print("=" * 80)
    print("STRATEGY COMPARISON: AGGRESSIVE V2 vs MOMENTUM")
    print("=" * 80)
    print(f"\nUniverse: {len(universe)} stocks")
    print("Take Profit (V2): 3%")
    print("Period 1: 2016-2023 (8 years)")
    print("Period 2: 2024-2025 (recent)")
    print("=" * 80)

    results = {}

    # ========================================================================
    # TEST 1: 8-Year Period (2016-2023)
    # ========================================================================
    print("\n" + "=" * 80)
    print("PERIOD 1: 8-YEAR BACKTEST (2016-2023)")
    print("=" * 80)

    # Aggressive V2
    print("\n--- AGGRESSIVE V2 ---")
    v2_8yr = AggressiveBacktesterV2(
        universe_tickers=universe,
        start_date='2016-01-01',
        end_date='2023-12-31',
        initial_capital=100000
    )
    v2_results_8yr = v2_8yr.run(verbose=True)

    v2_analyzer_8yr = PerformanceAnalyzer(
        returns=v2_results_8yr['returns'],
        benchmark_returns=v2_results_8yr['benchmark_returns'],
        equity_curve=v2_results_8yr['equity_curve'],
        trades=v2_results_8yr['trades'],
    )
    v2_metrics_8yr = v2_analyzer_8yr.calculate_all_metrics()

    # Momentum (Standard)
    print("\n--- MOMENTUM (STANDARD) ---")
    mom_8yr = Backtester(
        universe_tickers=universe,
        start_date='2016-01-01',
        end_date='2023-12-31',
        initial_capital=100000
    )
    mom_results_8yr = mom_8yr.run(verbose=True)

    mom_analyzer_8yr = PerformanceAnalyzer(
        returns=mom_results_8yr['returns'],
        benchmark_returns=mom_results_8yr['benchmark_returns'],
        equity_curve=mom_results_8yr['equity_curve'],
        trades=mom_results_8yr['trades'],
    )
    mom_metrics_8yr = mom_analyzer_8yr.calculate_all_metrics()

    results['8yr'] = {
        'v2': v2_metrics_8yr,
        'momentum': mom_metrics_8yr
    }

    # ========================================================================
    # TEST 2: Recent Period (2024-2025)
    # ========================================================================
    print("\n\n" + "=" * 80)
    print("PERIOD 2: RECENT (2024-2025)")
    print("=" * 80)

    # Aggressive V2
    print("\n--- AGGRESSIVE V2 ---")
    v2_recent = AggressiveBacktesterV2(
        universe_tickers=universe,
        start_date='2024-01-01',
        end_date='2025-12-31',
        initial_capital=100000
    )
    v2_results_recent = v2_recent.run(verbose=True)

    v2_analyzer_recent = PerformanceAnalyzer(
        returns=v2_results_recent['returns'],
        benchmark_returns=v2_results_recent['benchmark_returns'],
        equity_curve=v2_results_recent['equity_curve'],
        trades=v2_results_recent['trades'],
    )
    v2_metrics_recent = v2_analyzer_recent.calculate_all_metrics()

    # Momentum (Standard)
    print("\n--- MOMENTUM (STANDARD) ---")
    mom_recent = Backtester(
        universe_tickers=universe,
        start_date='2024-01-01',
        end_date='2025-12-31',
        initial_capital=100000
    )
    mom_results_recent = mom_recent.run(verbose=True)

    mom_analyzer_recent = PerformanceAnalyzer(
        returns=mom_results_recent['returns'],
        benchmark_returns=mom_results_recent['benchmark_returns'],
        equity_curve=mom_results_recent['equity_curve'],
        trades=mom_results_recent['trades'],
    )
    mom_metrics_recent = mom_analyzer_recent.calculate_all_metrics()

    results['recent'] = {
        'v2': v2_metrics_recent,
        'momentum': mom_metrics_recent
    }

    # ========================================================================
    # COMPARISON SUMMARY
    # ========================================================================
    print("\n\n" + "=" * 80)
    print("COMPARISON SUMMARY")
    print("=" * 80)

    metrics_to_show = ['total_return', 'cagr', 'volatility', 'sharpe_ratio', 'max_drawdown', 'win_rate']

    print("\n8-YEAR PERIOD (2016-2023)")
    print("-" * 80)
    print(f"{'Metric':<20} {'Aggressive V2':>20} {'Momentum':>20} {'Winner':>15}")
    print("-" * 80)

    for metric in metrics_to_show:
        v2_val = results['8yr']['v2'].get(metric, 0)
        mom_val = results['8yr']['momentum'].get(metric, 0)

        # Determine winner (higher is better for most, lower for volatility/drawdown)
        if metric in ['volatility', 'max_drawdown']:
            winner = 'V2' if abs(v2_val) < abs(mom_val) else 'Momentum'
        else:
            winner = 'V2' if v2_val > mom_val else 'Momentum'

        if metric in ['total_return', 'cagr', 'volatility', 'max_drawdown', 'win_rate']:
            print(f"{metric:<20} {v2_val:>19.2%} {mom_val:>19.2%} {winner:>15}")
        else:
            print(f"{metric:<20} {v2_val:>20.2f} {mom_val:>20.2f} {winner:>15}")

    print("\n\nRECENT PERIOD (2024-2025)")
    print("-" * 80)
    print(f"{'Metric':<20} {'Aggressive V2':>20} {'Momentum':>20} {'Winner':>15}")
    print("-" * 80)

    for metric in metrics_to_show:
        v2_val = results['recent']['v2'].get(metric, 0)
        mom_val = results['recent']['momentum'].get(metric, 0)

        if metric in ['volatility', 'max_drawdown']:
            winner = 'V2' if abs(v2_val) < abs(mom_val) else 'Momentum'
        else:
            winner = 'V2' if v2_val > mom_val else 'Momentum'

        if metric in ['total_return', 'cagr', 'volatility', 'max_drawdown', 'win_rate']:
            print(f"{metric:<20} {v2_val:>19.2%} {mom_val:>19.2%} {winner:>15}")
        else:
            print(f"{metric:<20} {v2_val:>20.2f} {mom_val:>20.2f} {winner:>15}")

    print("\n" + "=" * 80)
    print("COMPARISON COMPLETE")
    print("=" * 80)

    return results

if __name__ == '__main__':
    run_comparison()
