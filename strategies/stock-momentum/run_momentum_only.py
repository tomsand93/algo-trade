"""Run just the Momentum strategy for comparison"""
import config
from backtest import Backtester, PerformanceAnalyzer

universe = config.TOP_500_COMMON_STOCKS

print("=" * 70)
print("MOMENTUM STRATEGY BACKTEST (546 stocks)")
print("=" * 70)

# 8-Year Period
print("\n--- 8-YEAR PERIOD (2016-2023) ---")
mom_8yr = Backtester(
    universe_tickers=universe,
    start_date='2016-01-01',
    end_date='2023-12-31',
    initial_capital=100000
)
results_8yr = mom_8yr.run(verbose=True)

try:
    analyzer_8yr = PerformanceAnalyzer(
        returns=results_8yr['returns'],
        benchmark_returns=results_8yr['benchmark_returns'],
        equity_curve=results_8yr['equity_curve'],
        trades=results_8yr['trades'],
    )
    metrics_8yr = analyzer_8yr.calculate_all_metrics()
    print(f"\nTotal Return: {metrics_8yr['total_return']:.2%}")
    print(f"CAGR: {metrics_8yr['cagr']:.2%}")
    print(f"Volatility: {metrics_8yr['volatility']:.2%}")
    print(f"Sharpe Ratio: {metrics_8yr['sharpe_ratio']:.2f}")
    print(f"Max Drawdown: {metrics_8yr['max_drawdown']:.2%}")
    print(f"Win Rate: {metrics_8yr.get('win_rate', 0):.2%}")
except Exception as e:
    # Calculate manually if benchmark fails
    eq = results_8yr['equity_curve']
    final = eq['portfolio_value'].iloc[-1]
    initial = 100000
    total_ret = (final / initial) - 1
    cagr = (final / initial) ** (1/8) - 1
    print(f"\nFinal Portfolio: ${final:,.0f}")
    print(f"Total Return: {total_ret:.2%}")
    print(f"CAGR: {cagr:.2%}")

# Recent Period
print("\n\n--- RECENT PERIOD (2024-2025) ---")
mom_recent = Backtester(
    universe_tickers=universe,
    start_date='2024-01-01',
    end_date='2025-12-31',
    initial_capital=100000
)
results_recent = mom_recent.run(verbose=True)

try:
    analyzer_recent = PerformanceAnalyzer(
        returns=results_recent['returns'],
        benchmark_returns=results_recent['benchmark_returns'],
        equity_curve=results_recent['equity_curve'],
        trades=results_recent['trades'],
    )
    metrics_recent = analyzer_recent.calculate_all_metrics()
    print(f"\nTotal Return: {metrics_recent['total_return']:.2%}")
    print(f"CAGR: {metrics_recent['cagr']:.2%}")
    print(f"Volatility: {metrics_recent['volatility']:.2%}")
    print(f"Sharpe Ratio: {metrics_recent['sharpe_ratio']:.2f}")
    print(f"Max Drawdown: {metrics_recent['max_drawdown']:.2%}")
    print(f"Win Rate: {metrics_recent.get('win_rate', 0):.2%}")
except Exception as e:
    eq = results_recent['equity_curve']
    final = eq['portfolio_value'].iloc[-1]
    initial = 100000
    years = len(eq) / 12
    total_ret = (final / initial) - 1
    cagr = (final / initial) ** (1/years) - 1 if years > 0 else 0
    print(f"\nFinal Portfolio: ${final:,.0f}")
    print(f"Total Return: {total_ret:.2%}")
    print(f"CAGR: {cagr:.2%}")

print("\n" + "=" * 70)
print("MOMENTUM BACKTEST COMPLETE")
print("=" * 70)
