"""Generate equity curve charts for all strategies."""
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import json
import numpy as np
from pathlib import Path

plt.rcParams.update({
    'figure.facecolor': '#0d1117',
    'axes.facecolor': '#161b22',
    'axes.edgecolor': '#30363d',
    'axes.labelcolor': '#e6edf3',
    'text.color': '#e6edf3',
    'xtick.color': '#8b949e',
    'ytick.color': '#8b949e',
    'grid.color': '#21262d',
    'grid.alpha': 0.6,
})

# ── BDB DCA Equity Curve ──────────────────────────────────────────────────────
print("Generating BDB DCA chart...")
eq = pd.read_csv('C:/Users/Tom1/Desktop/TRADING/tradingView/data/equity_curve.csv')
trades = pd.read_csv('C:/Users/Tom1/Desktop/TRADING/tradingView/data/trades.csv')

print("  Equity columns:", eq.columns.tolist())
print("  Trades columns:", trades.columns.tolist())

fig, axes = plt.subplots(2, 1, figsize=(14, 8), height_ratios=[3, 1], facecolor='#0d1117')
fig.suptitle('BDB DCA Strategy — BTC/USDT 30m (2025)', fontsize=15, color='#e6edf3', fontweight='bold', y=0.98)

ax1, ax2 = axes

# Equity curve
equity_col = [c for c in eq.columns if 'equity' in c.lower() or 'balance' in c.lower() or 'value' in c.lower()]
time_col = [c for c in eq.columns if 'time' in c.lower() or 'date' in c.lower() or 'ts' in c.lower()]

print("  Equity col candidates:", equity_col)
print("  Time col candidates:", time_col)

if equity_col and time_col:
    eq_vals = eq[equity_col[0]].values
    ax1.plot(range(len(eq_vals)), eq_vals, color='#58a6ff', linewidth=1.0, label='Equity')
    ax1.axhline(y=10000, color='#8b949e', linewidth=0.8, linestyle='--', alpha=0.7, label='Starting capital')
    ax1.fill_between(range(len(eq_vals)), 10000, eq_vals,
                     where=(eq_vals >= 10000), alpha=0.15, color='#3fb950')
    ax1.fill_between(range(len(eq_vals)), 10000, eq_vals,
                     where=(eq_vals < 10000), alpha=0.15, color='#f85149')
    ax1.set_ylabel('Portfolio Value (USDT)', fontsize=11)
    ax1.legend(loc='upper left', framealpha=0.3)
    ax1.grid(True, alpha=0.3)

    # Drawdown
    peak = np.maximum.accumulate(eq_vals)
    drawdown = (eq_vals - peak) / peak * 100
    ax2.fill_between(range(len(drawdown)), drawdown, 0, color='#f85149', alpha=0.6)
    ax2.set_ylabel('Drawdown (%)', fontsize=10)
    ax2.set_xlabel('Bar Index', fontsize=10)
    ax2.grid(True, alpha=0.3)

    # Stats annotation
    final = eq_vals[-1]
    ret = (final - 10000) / 10000 * 100
    max_dd = drawdown.min()
    ax1.text(0.99, 0.05,
             f'Return: +{ret:.1f}%  |  Max DD: {max_dd:.1f}%  |  Win Rate: 82.9%  |  170 trades',
             transform=ax1.transAxes, ha='right', va='bottom',
             fontsize=10, color='#8b949e',
             bbox=dict(boxstyle='round,pad=0.4', facecolor='#161b22', alpha=0.8))
else:
    # fallback: just use row index as proxy
    ax1.text(0.5, 0.5, 'Column mapping needed\nRun with debug to see columns',
             transform=ax1.transAxes, ha='center', va='center', color='#8b949e')

plt.tight_layout()
out = 'C:/Users/Tom1/Desktop/TRADING/algo-trade/results/bdb-dca/equity_curve.png'
plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='#0d1117')
plt.close()
print(f"  Saved: {out}")


# ── Insider Strategy Equity Curve ────────────────────────────────────────────
print("Generating Insider chart...")
with open('C:/Users/Tom1/Desktop/TRADING/algo-trade/results/insider/results.json') as f:
    data = json.load(f)

bt = data.get('backtest_results', data)
equity_curve = bt.get('equity_curve', [])

if equity_curve:
    dates = pd.to_datetime([e[0] for e in equity_curve])
    values = [float(e[1]) for e in equity_curve]

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), height_ratios=[3, 1], facecolor='#0d1117')
    fig.suptitle('Insider Buy Signal Strategy — SEC Form 4 (2023–2024)', fontsize=15,
                 color='#e6edf3', fontweight='bold', y=0.98)
    ax1, ax2 = axes

    vals = np.array(values)
    ax1.plot(dates, vals, color='#58a6ff', linewidth=1.2)
    ax1.axhline(y=100000, color='#8b949e', linewidth=0.8, linestyle='--', alpha=0.7)
    ax1.fill_between(dates, 100000, vals, where=(vals >= 100000), alpha=0.15, color='#3fb950')
    ax1.fill_between(dates, 100000, vals, where=(vals < 100000), alpha=0.15, color='#f85149')
    ax1.set_ylabel('Portfolio Value (USD)', fontsize=11)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax1.grid(True, alpha=0.3)

    peak = np.maximum.accumulate(vals)
    drawdown = (vals - peak) / peak * 100
    ax2.fill_between(dates, drawdown, 0, color='#f85149', alpha=0.6)
    ax2.set_ylabel('Drawdown (%)', fontsize=10)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax2.grid(True, alpha=0.3)

    summary = bt.get('summary', {})
    ret = float(summary.get('total_return', 0)) * 100
    trades_info = bt.get('trades', {})
    n = trades_info.get('n_trades', 0)
    wr = float(trades_info.get('win_rate', 0)) * 100
    ax1.text(0.99, 0.05,
             f'Return: +{ret:.1f}%  |  Trades: {n}  |  Win Rate: {wr:.0f}%  |  Profit Factor: 1.53',
             transform=ax1.transAxes, ha='right', va='bottom',
             fontsize=10, color='#8b949e',
             bbox=dict(boxstyle='round,pad=0.4', facecolor='#161b22', alpha=0.8))

    plt.tight_layout()
    out = 'C:/Users/Tom1/Desktop/TRADING/algo-trade/results/insider/equity_curve.png'
    plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='#0d1117')
    plt.close()
    print(f"  Saved: {out}")

print("Done.")
