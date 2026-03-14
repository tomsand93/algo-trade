import json
with open('results/fvg-breakout/extensive_summary_20260206_190238.json') as f:
    d = json.load(f)
for cfg, v in d['configs'].items():
    print('Config %s: %s' % (cfg, v['label']))
    print('  Trades: %d  Win Rate: %.1f%%  PnL: $%.2f (%.2f%%)' % (
        v['total_trades'], v['win_rate'], v['total_pnl'], v['total_pnl_pct']))
    print('  Sharpe: %.2f  Max DD: %.2f%%  PF: %.2f  Avg R: %.3f' % (
        v['sharpe_ratio'], v['max_drawdown_pct']*100, v['profit_factor'], v['expectancy']))
    print()
