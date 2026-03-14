import json, glob, os
files = sorted(glob.glob('strategies/polymarket/data/backtest_results/*.json'))
for fp in files:
    with open(fp) as f:
        d = json.load(f)
    print('=== %s ===' % os.path.basename(fp))
    for k in ['total_trades','winning_trades','losing_trades','win_rate',
              'total_return_pct','profit_factor','max_drawdown_pct','sharpe_ratio',
              'total_pnl','initial_capital','final_capital']:
        if k in d:
            print('  %s: %s' % (k, d[k]))
    print()
