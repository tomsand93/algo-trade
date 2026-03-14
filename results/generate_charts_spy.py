"""
Regenerate all strategy equity curves with S&P 500 (SPY) comparison overlay.

Strategies covered:
  1. Stock Momentum ETF  — monthly equity CSV  (2023-2026)
  2. Insider Buy Signal  — results JSON        (2023-2024)
  3. FVG Breakout C      — trade CSV (best config: BE OFF, both dirs) (2025)
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yfinance as yf  # noqa: E402

# -- Paths --------------------------------------------------------------------
ROOT  = Path(__file__).parent.parent          # algo-trade/
STRAT = ROOT / 'strategies'
RES   = ROOT / 'results'
PROD  = Path('C:/Users/Tom1/Desktop/TRADING/production')

# -- Dark theme ---------------------------------------------------------------
DARK   = '#0d1117'
PANEL  = '#161b22'
BORDER = '#30363d'
TEXT   = '#e6edf3'
MUTED  = '#8b949e'
BLUE   = '#58a6ff'
ORANGE = '#f0883e'
GREEN  = '#3fb950'
RED    = '#f85149'

plt.rcParams.update({
    'figure.facecolor': DARK, 'axes.facecolor': PANEL,
    'axes.edgecolor': BORDER, 'axes.labelcolor': TEXT,
    'text.color': TEXT, 'xtick.color': MUTED, 'ytick.color': MUTED,
    'grid.color': '#21262d', 'grid.alpha': 0.5,
})


# -- Helpers ------------------------------------------------------------------

def fetch_spy(start, end):
    df = yf.download('SPY', start=start, end=end, progress=False, auto_adjust=True)
    return df['Close'].dropna()


def normalize(series):
    arr = np.array(series, dtype=float).flatten()
    return arr / arr[0] * 100


def scalar(x):
    return float(np.array(x).flat[0])


def save(fig, path):
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=DARK)
    plt.close(fig)
    print(f"  Saved: {path}")


def stat_box(ax, text):
    ax.text(0.99, 0.05, text, transform=ax.transAxes, ha='right', va='bottom',
            fontsize=9, color=MUTED,
            bbox=dict(boxstyle='round,pad=0.4', facecolor=PANEL, alpha=0.85))


def make_figure(title):
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), height_ratios=[3, 1], facecolor=DARK)
    fig.suptitle(title, fontsize=14, color=TEXT, fontweight='bold')
    return fig, axes[0], axes[1]


def draw_equity(ax, dates, eq_norm, color=BLUE, label='Strategy', linewidth=1.3):
    ax.plot(dates, eq_norm, color=color, linewidth=linewidth, label=label, zorder=3)
    ax.axhline(100, color=MUTED, linewidth=0.7, linestyle=':', alpha=0.6)
    ax.fill_between(dates, 100, eq_norm,
                    where=(np.array(eq_norm) >= 100), alpha=0.12, color=GREEN)
    ax.fill_between(dates, 100, eq_norm,
                    where=(np.array(eq_norm) < 100), alpha=0.12, color=RED)
    ax.set_ylabel('Value (Normalised to 100)', fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))


def finish_legend(ax):
    ax.legend(loc='upper left', framealpha=0.6, fontsize=10,
              facecolor=PANEL, edgecolor=BORDER,
              labelcolor=TEXT, handlelength=2.2)


def draw_drawdown(ax, dates, eq_norm):
    eq = np.array(eq_norm, dtype=float)
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak * 100
    ax.fill_between(dates, dd, 0, color=RED, alpha=0.55)
    ax.set_ylabel('Drawdown (%)', fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))


def add_benchmark(ax, dates, values, color=ORANGE, label='S&P 500 (SPY)'):
    ax.plot(dates, values, color=color, linewidth=1.5,
            linestyle='--', alpha=0.9, label=label, zorder=2)


def trades_to_daily_equity(dates, pnls, start_capital, date_range_start, date_range_end):
    df = pd.DataFrame({'date': pd.to_datetime(dates), 'pnl': pnls})
    df = df.set_index('date').sort_index()
    daily = df['pnl'].resample('D').sum()
    idx = pd.date_range(date_range_start, date_range_end, freq='D')
    daily = daily.reindex(idx, fill_value=0)
    equity = start_capital + daily.cumsum()
    return equity


# =============================================================================
# 1. STOCK MOMENTUM ETF  (2023-2026)
# =============================================================================
print("1. Stock Momentum ETF...")

eq = pd.read_csv(PROD / 'stock_momentum/results/equity_curve.csv')
eq['date'] = pd.to_datetime(eq['date'])
eq = eq.set_index('date').sort_index()
eq_vals = eq['portfolio_value'].dropna()

start = str(eq_vals.index[0].date())
end   = str(eq_vals.index[-1].date())
spy   = fetch_spy(start, end)
spy_a = spy.reindex(eq_vals.index, method='ffill').dropna()
common = eq_vals.index.intersection(spy_a.index)
eq_c, spy_c = eq_vals.loc[common], spy_a.loc[common]

eq_norm  = normalize(eq_c.values)
spy_norm = normalize(spy_c.values)

fig, ax1, ax2 = make_figure('Stock Momentum ETF vs S&P 500  (2023-2026, Monthly Rebalance)')
draw_equity(ax1, common, eq_norm, label='Stock Momentum ETF')
add_benchmark(ax1, common, spy_norm)
finish_legend(ax1)
draw_drawdown(ax2, common, eq_norm)

strat_ret = scalar(eq_norm[-1]) - 100
spy_ret   = scalar(spy_norm[-1]) - 100
stat_box(ax1, f'Strategy: +{strat_ret:.1f}%  |  SPY: +{spy_ret:.1f}%  |  Alpha: {strat_ret - spy_ret:+.1f}%'
              f'  |  Sharpe: 0.94  |  Max DD: -22.5%')
plt.tight_layout()
save(fig, RES / 'stock-momentum/equity_curve_vs_spy.png')


# =============================================================================
# 2. INSIDER BUY SIGNAL  (2023-2024)
# =============================================================================
print("2. Insider Buy Signal...")

with open(RES / 'insider/results.json') as f:
    data = json.load(f)

bt      = data.get('backtest_results', data)
ec      = bt.get('equity_curve', [])
dates_i = pd.to_datetime([e[0] for e in ec])
vals_i  = np.array([float(e[1]) for e in ec])

start, end = '2023-01-01', '2025-01-01'
spy   = fetch_spy(start, end)
spy_a = spy[spy.index >= pd.Timestamp(start)]

eq_norm  = normalize(vals_i)
spy_norm = normalize(spy_a.values)

fig, ax1, ax2 = make_figure('Insider Buy Signal — SEC Form 4 vs S&P 500  (2023-2024)')
draw_equity(ax1, dates_i, eq_norm, label='Insider Strategy')
add_benchmark(ax1, spy_a.index, spy_norm)
finish_legend(ax1)
draw_drawdown(ax2, dates_i, eq_norm)

trades_info = bt.get('trades', {})
n  = trades_info.get('n_trades', 29)
wr = float(trades_info.get('win_rate', 0.448)) * 100
strat_ret = scalar(eq_norm[-1]) - 100
spy_ret   = scalar(spy_norm[-1]) - 100
stat_box(ax1, f'Strategy: +{strat_ret:.1f}%  |  SPY: +{spy_ret:.1f}%  |  Alpha: {strat_ret - spy_ret:+.1f}%'
              f'  |  {n} trades  |  WR: {wr:.0f}%  |  PF: 1.53')
plt.tight_layout()
save(fig, RES / 'insider/equity_curve.png')


# =============================================================================
# 3. FVG BREAKOUT — Config C: Both dirs + Break-even OFF  (best, 2025)
# =============================================================================
print("3. FVG Breakout (Config C - best)...")

fvg_csv = STRAT / 'fvg-breakout/archive/results/extensive/trades_config_C_20260206_190238.csv'
trades  = pd.read_csv(fvg_csv)
trades['exit_dt'] = pd.to_datetime(trades['exit_time'], utc=True).dt.tz_localize(None)
trades = trades.sort_values('exit_dt')

start, end = '2025-02-01', '2026-02-01'
eq_fvg = trades_to_daily_equity(
    trades['exit_dt'], trades['pnl'], 100_000, start, end)

spy   = fetch_spy(start, end)
spy_a = spy.reindex(eq_fvg.index, method='ffill').dropna()
common = eq_fvg.index.intersection(spy_a.index)

eq_norm  = normalize(eq_fvg.loc[common].values)
spy_norm = normalize(spy_a.loc[common].values)

# FVG is nearly flat (+0.43%) so use dual y-axis to keep both lines visible
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), height_ratios=[3, 1], facecolor=DARK)
fig.suptitle('FVG Breakout (Config C: Both Dirs, No Break-Even) vs S&P 500  (Feb 2025 - Jan 2026)',
             fontsize=14, color=TEXT, fontweight='bold')
ax1.set_facecolor(PANEL)
ax2.set_facecolor(PANEL)

margin = max(0.5, (eq_norm.max() - eq_norm.min()) * 0.3)
ax1.set_ylim(eq_norm.min() - margin, eq_norm.max() + margin)
ax1.plot(common, eq_norm, color=BLUE, linewidth=1.3, label='FVG Breakout (Config C)', zorder=3)
ax1.axhline(100, color=MUTED, linewidth=0.7, linestyle=':', alpha=0.6)
ax1.fill_between(common, 100, eq_norm, where=(eq_norm >= 100), alpha=0.2, color=GREEN)
ax1.fill_between(common, 100, eq_norm, where=(eq_norm < 100), alpha=0.2, color=RED)
ax1.set_ylabel('Strategy (Normalised to 100)', fontsize=11, color=BLUE)
ax1.tick_params(axis='y', colors=BLUE)
ax1.grid(True, alpha=0.3)
ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))

ax1r = ax1.twinx()
ax1r.set_facecolor('none')
ax1r.plot(common, spy_norm, color=ORANGE, linewidth=1.5, linestyle='--',
          alpha=0.9, label='S&P 500 (SPY)', zorder=2)
ax1r.set_ylabel('S&P 500 (Normalised to 100)', fontsize=11, color=ORANGE)
ax1r.tick_params(axis='y', colors=ORANGE)
ax1r.spines['right'].set_color(BORDER)

lines1, labs1 = ax1.get_legend_handles_labels()
lines2, labs2 = ax1r.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labs1 + labs2,
           loc='upper left', framealpha=0.6, fontsize=10,
           facecolor=PANEL, edgecolor=BORDER, labelcolor=TEXT)

draw_drawdown(ax2, common, eq_norm)

strat_ret = scalar(eq_norm[-1]) - 100
spy_ret   = scalar(spy_norm[-1]) - 100
stat_box(ax1, f'Strategy: +{strat_ret:.2f}%  |  SPY: +{spy_ret:.1f}%  |  Alpha: {strat_ret - spy_ret:+.1f}%'
              f'  |  3,474 trades  |  WR: 39.4%  |  PF: 1.36  |  Sharpe: 1.74')
plt.tight_layout()
save(fig, RES / 'fvg-breakout/equity_curve_vs_spy.png')


print("\nAll charts generated.")
