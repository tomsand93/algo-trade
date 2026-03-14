"""
Regenerate all strategy equity curves with S&P 500 (SPY) comparison overlay.
Each chart uses real backtest data, proper time axis, and SPY / BTC benchmarks.

Strategies covered:
  1. Stock Momentum ETF  — monthly equity CSV  (2023–2026)
  2. BDB DCA             — daily equity CSV    (2025)
  3. Insider Buy Signal  — results JSON        (2023–2024)
  4. FVG Breakout C      — trade CSV (best config: BE OFF, both dirs) (2025)
  5. Candlestick Pro     — live backtest via subprocess (2024–2026)
  6. Orderbook L2        — summary stats bar chart (4 trades, early dev)
"""

import io
import json
import re
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT   = Path(__file__).parent.parent          # algo-trade/
STRAT  = ROOT / 'strategies'
RES    = ROOT / 'results'
PROD   = Path('C:/Users/Tom1/Desktop/TRADING/production')
TVIEW  = Path('C:/Users/Tom1/Desktop/TRADING/tradingView')
PYTHON = Path('C:/Users/Tom1/miniconda3/envs/trade312/python.exe')

# ── Dark theme ───────────────────────────────────────────────────────────────
DARK   = '#0d1117'
PANEL  = '#161b22'
BORDER = '#30363d'
TEXT   = '#e6edf3'
MUTED  = '#8b949e'
BLUE   = '#58a6ff'
ORANGE = '#f0883e'
GREEN  = '#3fb950'
RED    = '#f85149'
GOLD   = '#d29922'

plt.rcParams.update({
    'figure.facecolor': DARK, 'axes.facecolor': PANEL,
    'axes.edgecolor': BORDER, 'axes.labelcolor': TEXT,
    'text.color': TEXT, 'xtick.color': MUTED, 'ytick.color': MUTED,
    'grid.color': '#21262d', 'grid.alpha': 0.5,
})


# ── Helpers ──────────────────────────────────────────────────────────────────

def fetch_spy(start, end):
    df = yf.download('SPY', start=start, end=end, progress=False, auto_adjust=True)
    return df['Close'].dropna()


def fetch_btc(start, end):
    df = yf.download('BTC-USD', start=start, end=end, progress=False, auto_adjust=True)
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


def make_figure(title, ncols=1):
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
    ax.legend(loc='upper left', framealpha=0.3, fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))


def draw_drawdown(ax, dates, eq_norm):
    eq = np.array(eq_norm, dtype=float)
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak * 100
    ax.fill_between(dates, dd, 0, color=RED, alpha=0.55)
    ax.set_ylabel('Drawdown (%)', fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    return dd


def add_benchmark(ax, dates, values, color=ORANGE, label='S&P 500 (SPY)'):
    ax.plot(dates, values, color=color, linewidth=1.2,
            linestyle='--', alpha=0.85, label=label, zorder=2)


def trades_to_daily_equity(dates, pnls, start_capital, date_range_start, date_range_end):
    """Convert trade exit dates + pnls to a daily equity series."""
    df = pd.DataFrame({'date': pd.to_datetime(dates), 'pnl': pnls})
    df = df.set_index('date').sort_index()
    daily = df['pnl'].resample('D').sum()
    idx = pd.date_range(date_range_start, date_range_end, freq='D')
    daily = daily.reindex(idx, fill_value=0)
    equity = start_capital + daily.cumsum()
    return equity


# ═══════════════════════════════════════════════════════════════════════════
# 1. STOCK MOMENTUM ETF  (2023–2026)
# ═══════════════════════════════════════════════════════════════════════════
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

fig, ax1, ax2 = make_figure('Stock Momentum ETF vs S&P 500  (2023–2026, Monthly Rebalance)')
draw_equity(ax1, common, eq_norm, label='Stock Momentum ETF')
add_benchmark(ax1, common, spy_norm)
draw_drawdown(ax2, common, eq_norm)

strat_ret = scalar(eq_norm[-1]) - 100
spy_ret   = scalar(spy_norm[-1]) - 100
stat_box(ax1, f'Strategy: +{strat_ret:.1f}%  |  SPY: +{spy_ret:.1f}%  |  Alpha: {strat_ret - spy_ret:+.1f}%'
              f'  |  Sharpe: 0.94  |  Max DD: −22.5%')
plt.tight_layout()
save(fig, RES / 'stock-momentum/equity_curve_vs_spy.png')


# ═══════════════════════════════════════════════════════════════════════════
# 2. BDB DCA  —  BTC/USDT 30m  (2025)
# ═══════════════════════════════════════════════════════════════════════════
print("2. BDB DCA...")

eq = pd.read_csv(TVIEW / 'data/equity_curve.csv')
eq['dt'] = pd.to_datetime(eq['datetime_utc'], utc=True)
eq = eq.set_index('dt').sort_index()

start, end = '2025-01-01', '2026-02-01'
eq_win = eq.loc[start:end, 'equity'].resample('D').last().dropna()

spy  = fetch_spy(start, end)
btc  = fetch_btc(start, end)

common_start = max(eq_win.index[0].date(), spy.index[0].date())
eq_win   = eq_win[eq_win.index.date >= common_start]
spy_a    = spy[spy.index >= pd.Timestamp(common_start)]
btc_a    = btc[btc.index >= pd.Timestamp(common_start)]

eq_norm  = normalize(eq_win.values)
spy_norm = normalize(spy_a.values)
btc_norm = normalize(btc_a.values)

fig, ax1, ax2 = make_figure('BDB DCA — BTC/USDT 30m vs S&P 500 & BTC  (2025)')
draw_equity(ax1, eq_win.index, eq_norm, label='BDB DCA')
add_benchmark(ax1, spy_a.index, spy_norm)
add_benchmark(ax1, btc_a.index, btc_norm, color=GOLD, label='BTC Buy & Hold')
draw_drawdown(ax2, eq_win.index, eq_norm)

strat_ret = scalar(eq_norm[-1]) - 100
spy_ret   = scalar(spy_norm[-1]) - 100
btc_ret   = scalar(btc_norm[-1]) - 100
stat_box(ax1, f'Strategy: +{strat_ret:.1f}%  |  SPY: +{spy_ret:.1f}%  |  BTC: +{btc_ret:.1f}%'
              f'  |  Alpha vs SPY: {strat_ret - spy_ret:+.1f}%  |  WR: 82.9%  |  170 trades')
plt.tight_layout()
save(fig, RES / 'bdb-dca/equity_curve.png')


# ═══════════════════════════════════════════════════════════════════════════
# 3. INSIDER BUY SIGNAL  (2023–2024)
# ═══════════════════════════════════════════════════════════════════════════
print("3. Insider Buy Signal...")

with open(RES / 'insider/results.json') as f:
    data = json.load(f)

bt  = data.get('backtest_results', data)
ec  = bt.get('equity_curve', [])
dates_i = pd.to_datetime([e[0] for e in ec])
vals_i  = np.array([float(e[1]) for e in ec])

start, end = '2023-01-01', '2025-01-01'
spy   = fetch_spy(start, end)
spy_a = spy[spy.index >= pd.Timestamp(start)]

eq_norm  = normalize(vals_i)
spy_norm = normalize(spy_a.values)

fig, ax1, ax2 = make_figure('Insider Buy Signal — SEC Form 4 vs S&P 500  (2023–2024)')
draw_equity(ax1, dates_i, eq_norm, label='Insider Strategy')
add_benchmark(ax1, spy_a.index, spy_norm)
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


# ═══════════════════════════════════════════════════════════════════════════
# 4. FVG BREAKOUT — Config C: Both dirs + Break-even OFF  (best, 2025)
# ═══════════════════════════════════════════════════════════════════════════
print("4. FVG Breakout (Config C — best)...")

fvg_csv = STRAT / 'fvg-breakout/archive/results/extensive/trades_config_C_20260206_190238.csv'
trades  = pd.read_csv(fvg_csv)
trades['exit_dt'] = pd.to_datetime(trades['exit_time'], utc=True).dt.tz_localize(None)
trades = trades.sort_values('exit_dt')

start, end = '2025-02-01', '2026-02-01'
eq_fvg = trades_to_daily_equity(
    trades['exit_dt'], trades['pnl'], 100_000, start, end)

spy  = fetch_spy(start, end)
spy_a = spy.reindex(eq_fvg.index, method='ffill').dropna()
common = eq_fvg.index.intersection(spy_a.index)

eq_norm  = normalize(eq_fvg.loc[common].values)
spy_norm = normalize(spy_a.loc[common].values)

fig, ax1, ax2 = make_figure('FVG Breakout (Config C: Both Dirs, No Break-Even) vs S&P 500  (Feb 2025 – Jan 2026)')
draw_equity(ax1, common, eq_norm, label='FVG Breakout (Config C)')
add_benchmark(ax1, common, spy_norm)
draw_drawdown(ax2, common, eq_norm)

strat_ret = scalar(eq_norm[-1]) - 100
spy_ret   = scalar(spy_norm[-1]) - 100
stat_box(ax1, f'Strategy: +{strat_ret:.2f}%  |  SPY: +{spy_ret:.1f}%  |  Alpha: {strat_ret - spy_ret:+.1f}%'
              f'  |  3,474 trades  |  WR: 39.4%  |  PF: 1.36  |  Sharpe: 1.74')
plt.tight_layout()
save(fig, RES / 'fvg-breakout/equity_curve_vs_spy.png')


# ═══════════════════════════════════════════════════════════════════════════
# 5. CANDLESTICK PRO — BTC 4H (2024–2026) — real backtest output
# ═══════════════════════════════════════════════════════════════════════════
print("5. Candlestick Pro (running live backtest)...")

cs_archive = STRAT / 'candlestick-pro/archive'
cs_src     = STRAT / 'candlestick-pro'

result = subprocess.run(
    [str(PYTHON), str(cs_archive / 'btc_4h_backtest.py')],
    capture_output=True, text=True,
    env={**__import__('os').environ, 'PYTHONPATH': str(cs_src)},
    cwd=str(cs_archive),
)
output = result.stdout

# Parse trade rows: "  N  YYYY-MM-DD  YYYY-MM-DD  pattern  direction  $xxx  $xxx  $±pnl  bars  reason"
pattern = re.compile(
    r'^\s+(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(\d{4}-\d{2}-\d{2})\s+\S+\s+\S+\s+'
    r'\S+\s+\S+\s+\$([+-]?[\d,]+\.\d+)'
)
rows = []
for line in output.splitlines():
    m = pattern.match(line)
    if m:
        exit_date = pd.Timestamp(m.group(3))
        pnl       = float(m.group(4).replace(',', ''))
        rows.append({'exit_date': exit_date, 'pnl': pnl})

if rows:
    cs_trades = pd.DataFrame(rows)
    start = str(cs_trades['exit_date'].min().date())
    end   = str(cs_trades['exit_date'].max().date())

    eq_cs = trades_to_daily_equity(
        cs_trades['exit_date'], cs_trades['pnl'], 10_000, start, end)

    spy = fetch_spy('2024-02-01', '2026-03-15')
    btc = fetch_btc('2024-02-01', '2026-03-15')
    spy_a = spy.reindex(eq_cs.index, method='ffill').dropna()
    btc_a = btc.reindex(eq_cs.index, method='ffill').dropna()
    common = eq_cs.index.intersection(spy_a.index).intersection(btc_a.index)

    eq_norm  = normalize(eq_cs.loc[common].values)
    spy_norm = normalize(spy_a.loc[common].values)
    btc_norm = normalize(btc_a.loc[common].values)

    fig, ax1, ax2 = make_figure('Candlestick Pro — BTC 4H vs S&P 500 & BTC  (2024–2026)  ⚠ In Development')
    draw_equity(ax1, common, eq_norm, label='Candlestick Pro (live config)')
    add_benchmark(ax1, common, spy_norm)
    add_benchmark(ax1, common, btc_norm, color=GOLD, label='BTC Buy & Hold')
    ax1.text(0.5, 0.48, 'IN DEVELOPMENT — Not profitable\nNeeds strict_trend=True fix',
             transform=ax1.transAxes, ha='center', va='center', fontsize=12,
             color=RED, alpha=0.3, fontweight='bold', rotation=15)
    draw_drawdown(ax2, common, eq_norm)

    strat_ret = scalar(eq_norm[-1]) - 100
    spy_ret   = scalar(spy_norm[-1]) - 100
    btc_ret   = scalar(btc_norm[-1]) - 100
    n_trades  = len(rows)
    stat_box(ax1, f'Strategy: {strat_ret:.1f}%  |  SPY: +{spy_ret:.1f}%  |  BTC: +{btc_ret:.1f}%'
                  f'  |  {n_trades} trades  |  WR: 32.3%  |  PF: 0.49')
    plt.tight_layout()
    save(fig, RES / 'candlestick-pro/equity_curve_vs_spy.png')
else:
    print("  WARNING: Could not parse candlestick-pro backtest output — skipping chart.")
    print("  stderr:", result.stderr[:300])


# ═══════════════════════════════════════════════════════════════════════════
# 6. ORDERBOOK L2 — summary bar chart (only 4 trades, early dev)
# ═══════════════════════════════════════════════════════════════════════════
print("6. Orderbook L2 (stats bar chart)...")

ob_summary = {
    'Total Return': -0.12,
    'Win Rate': 25.0,
    'Profit Factor': 0.53,
    'Sharpe Ratio': -0.13,
    'Max Drawdown': -1.69,
}

fig, ax = plt.subplots(figsize=(10, 5), facecolor=DARK)
ax.set_facecolor(PANEL)
fig.suptitle('Orderbook L2 — Strategy Stats  (4 trades, Early Development)',
             fontsize=13, color=TEXT, fontweight='bold')

labels = list(ob_summary.keys())
values = list(ob_summary.values())
colors = [GREEN if v > 0 else RED for v in values]

bars = ax.bar(labels, values, color=colors, alpha=0.75, edgecolor=BORDER)
ax.axhline(0, color=MUTED, linewidth=0.8)
for bar, val in zip(bars, values):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + (0.05 if val >= 0 else -0.15),
            f'{val:.2f}', ha='center', va='bottom', color=TEXT, fontsize=10)

ax.set_ylabel('Value', fontsize=11)
ax.tick_params(colors=MUTED)
ax.text(0.5, 0.85,
        'EARLY DEVELOPMENT — 4 trades insufficient for conclusions\n'
        'Needs 200+ real L2 book snapshots for validation',
        transform=ax.transAxes, ha='center', va='top',
        fontsize=10, color=MUTED, style='italic')
plt.tight_layout()
save(fig, RES / 'orderbook/equity.png')


print("\nAll charts generated.")
