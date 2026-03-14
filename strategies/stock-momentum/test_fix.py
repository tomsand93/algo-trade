"""Test the fixed backtest"""
import sys
import os
sys.path.insert(0, r"C:\Users\Tom1\Desktop\TRADING\production\stock_momentum")
import config_moderate as config
sys.modules['config'] = config

from backtest import Backtester, PerformanceAnalyzer

print('Testing FIXED backtest on 2022-2023 period...')
print(f'Cash buffer: {config.MIN_CASH_BUFFER*100:.0f}% (percentage-based now)\n')

backtester = Backtester(
    universe_tickers=config.DEFAULT_UNIVERSE,
    start_date='2022-01-01',
    end_date='2023-12-31',
    initial_capital=100000
)

results = backtester.run(verbose=True)

analyzer = PerformanceAnalyzer(
    returns=results['returns'],
    benchmark_returns=results['benchmark_returns'],
    equity_curve=results['equity_curve'],
    trades=results['trades'],
)

metrics = analyzer.calculate_all_metrics()

print('\n' + '='*80)
print('BEFORE FIX vs AFTER FIX (2022-2023)')
print('='*80)
print(f'                    BEFORE (Buggy)  AFTER (Fixed)')
print(f'CAGR:                    128.78%     {metrics["cagr"]:.2%}')
print(f'Volatility:              126.86%     {metrics["volatility"]:.2%}')
print(f'Max Drawdown:            -79.60%     {metrics["max_drawdown"]:.2%}')
print(f'Sharpe Ratio:               1.02     {metrics["sharpe_ratio"]:.2f}')
print(f'Total Trades:                280     {metrics["num_trades"]:.0f}')
print('='*80)
