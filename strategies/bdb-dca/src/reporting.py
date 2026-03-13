"""
Reporting module: console output, CSV export, Pine comparison.

Produces formatted tables for all metrics, exports trades to CSV,
and prints Pine Script target comparison.
"""

import csv
import os
from datetime import datetime, timezone
from typing import Optional

from .models import BacktestResult, TradeRecord
from .metrics import ExtendedMetrics, DailyPnLStats, compute_extended_metrics
from .scoring import (
    SymbolScoreBreakdown, compute_symbol_score,
    TradeQualityBreakdown
)


def print_full_report(result: BacktestResult,
                      pine_targets: Optional[dict] = None,
                      risk_engine=None,
                      bars: Optional[list] = None):
    """Print complete backtest report to console."""
    metrics = compute_extended_metrics(result)

    print()
    print("=" * 65)
    print("  BACKTEST REPORT")
    print("=" * 65)

    _print_performance_summary(metrics)
    _print_trade_stats(metrics)
    _print_drawdown_stats(metrics, result)
    _print_daily_pnl_stats(metrics.daily_pnl)

    if pine_targets:
        _print_pine_comparison(metrics, pine_targets)

    # Symbol score
    score = compute_symbol_score(result, bars=bars)
    _print_symbol_score(score)

    if risk_engine is not None:
        _print_risk_summary(risk_engine)

    print()


def print_trade_list(result: BacktestResult, max_trades: int = 20):
    """Print a table of individual trades."""
    trades = result.trades
    n = min(max_trades, len(trades))

    print()
    print(f"  TRADE LIST (showing {n} of {len(trades)})")
    print(f"  {'-'*75}")
    print(f"  {'#':>3} {'EntryBar':>8} {'EntryPx':>10} {'ExitBar':>8} "
          f"{'ExitPx':>10} {'Qty':>10} {'PnL':>10} {'Net%':>7}")
    print(f"  {'-'*3} {'-'*8} {'-'*10} {'-'*8} {'-'*10} {'-'*10} {'-'*10} {'-'*7}")

    for i, t in enumerate(trades[:n]):
        entry_val = t.entry_price * t.entry_qty
        pct = t.pnl_net / entry_val * 100 if entry_val > 0 else 0.0
        print(f"  {i+1:>3} {t.entry_bar_index:>8} {t.entry_price:>10.2f} "
              f"{t.exit_bar_index:>8} {t.exit_price:>10.2f} "
              f"{t.entry_qty:>10.6f} {t.pnl_net:>10.2f} {pct:>6.2f}%")

    if len(trades) > n:
        print(f"  ... {len(trades) - n} more trades not shown")
    print()


def export_trades_csv(result: BacktestResult, filepath: str):
    """Export all trades to CSV."""
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)

    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'trade_num', 'entry_id', 'entry_bar', 'entry_price',
            'exit_bar', 'exit_price', 'qty', 'pnl_gross',
            'commission', 'pnl_net', 'return_pct'
        ])
        for i, t in enumerate(result.trades):
            entry_val = t.entry_price * t.entry_qty
            pct = t.pnl_net / entry_val * 100 if entry_val > 0 else 0.0
            writer.writerow([
                i + 1, t.entry_id, t.entry_bar_index, f"{t.entry_price:.2f}",
                t.exit_bar_index, f"{t.exit_price:.2f}",
                f"{t.entry_qty:.8f}", f"{t.pnl_gross:.4f}",
                f"{t.commission_total:.4f}", f"{t.pnl_net:.4f}",
                f"{pct:.4f}"
            ])

    print(f"  Trades exported to {filepath} ({len(result.trades)} rows)")


def export_equity_csv(result: BacktestResult, filepath: str):
    """Export equity curve to CSV."""
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)

    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp_ms', 'datetime_utc', 'equity'])
        for ts, eq in result.equity_curve:
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            writer.writerow([ts, dt.strftime("%Y-%m-%d %H:%M"), f"{eq:.2f}"])

    print(f"  Equity curve exported to {filepath} ({len(result.equity_curve)} rows)")


# =============================================================================
# Internal print helpers
# =============================================================================

def _print_performance_summary(m: ExtendedMetrics):
    print()
    print("  PERFORMANCE SUMMARY")
    print(f"  {'-'*40}")
    print(f"  {'Net Profit:':<25} {m.net_profit:>12.2f} USDT ({m.net_profit_pct:+.2f}%)")
    print(f"  {'Profit Factor:':<25} {m.profit_factor:>12.2f}")
    print(f"  {'Sharpe Ratio:':<25} {m.sharpe_ratio:>12.2f}")
    print(f"  {'Expectancy:':<25} {m.expectancy:>12.2f} USDT")
    print(f"  {'Exposure:':<25} {m.exposure_pct:>11.1f}%")


def _print_trade_stats(m: ExtendedMetrics):
    print()
    print("  TRADE STATISTICS")
    print(f"  {'-'*40}")
    print(f"  {'Total Trades:':<25} {m.total_trades:>12}")
    print(f"  {'Win Rate:':<25} {m.win_rate:>11.2f}%")
    print(f"  {'Winning Trades:':<25} {m.winning_trades:>12}")
    print(f"  {'Losing Trades:':<25} {m.losing_trades:>12}")
    print(f"  {'Avg Trade PnL:':<25} {m.avg_trade_pnl:>12.2f} USDT")
    print(f"  {'Avg Trade Return:':<25} {m.avg_trade_pct:>11.2f}%")
    print(f"  {'Avg Win:':<25} {m.avg_win:>12.2f} USDT")
    print(f"  {'Avg Loss:':<25} {m.avg_loss:>12.2f} USDT")
    print(f"  {'Largest Win:':<25} {m.largest_win:>12.2f} USDT")
    print(f"  {'Largest Loss:':<25} {m.largest_loss:>12.2f} USDT")
    print(f"  {'Max Consec Wins:':<25} {m.max_consecutive_wins:>12}")
    print(f"  {'Max Consec Losses:':<25} {m.max_consecutive_losses:>12}")
    print(f"  {'Avg Time in Trade:':<25} {m.avg_time_in_trade_hours:>10.1f} hrs")


def _print_drawdown_stats(m: ExtendedMetrics, result: BacktestResult):
    print()
    print("  DRAWDOWN")
    print(f"  {'-'*40}")
    print(f"  {'Max DD (MtM):':<25} {m.max_drawdown:>12.2f} USDT")
    print(f"  {'Max DD (Closed-trade):':<25} {m.closed_trade_max_drawdown:>12.2f} USDT")
    print(f"  {'Max DD Duration:':<25} {m.max_dd_duration_bars:>8} bars ({m.max_dd_duration_hours:.0f} hrs)")
    print(f"  {'Max Single Loss:':<25} {m.max_single_position_loss:>12.2f} USDT ({m.max_single_position_loss_pct:.2f}%)")


def _print_daily_pnl_stats(stats: Optional[DailyPnLStats]):
    if stats is None or not stats.daily_pnls:
        return

    print()
    print("  DAILY PnL DISTRIBUTION")
    print(f"  {'-'*40}")
    print(f"  {'Mean:':<25} {stats.mean:>11.4f}%")
    print(f"  {'Std Dev:':<25} {stats.std:>11.4f}%")
    print(f"  {'Worst Day:':<25} {stats.min_pnl:>11.4f}%")
    print(f"  {'Best Day:':<25} {stats.max_pnl:>11.4f}%")
    print(f"  {'Skewness:':<25} {stats.skewness:>11.4f}")
    print(f"  {'Kurtosis (excess):':<25} {stats.kurtosis:>11.4f}")

    if stats.percentiles:
        print(f"  {'Percentiles:':<25}", end="")
        pcts = sorted(stats.percentiles.keys())
        for p in pcts:
            print(f" p{p}={stats.percentiles[p]:.3f}%", end="")
        print()


def _print_pine_comparison(m: ExtendedMetrics, targets: dict):
    print()
    print("  PINE SCRIPT COMPARISON")
    print(f"  {'-'*65}")
    print(f"  {'Metric':<22} {'Result':>12} {'Target':>12} {'Diff':>10} {'Status':>8}")
    print(f"  {'-'*22} {'-'*12} {'-'*12} {'-'*10} {'-'*8}")

    comparisons = [
        ("Total Trades", m.total_trades, targets.get("total_trades", 0), "", 3),
        ("Win Rate", m.win_rate, targets.get("win_rate", 0), "%", 1.0),
        ("Net Profit", m.net_profit, targets.get("net_profit", 0), " USDT", 19.0),
        ("Net Profit %", m.net_profit_pct, targets.get("net_profit_pct", 0), "%", 0.5),
        ("Profit Factor", m.profit_factor, targets.get("profit_factor", 0), "", 0.1),
        ("Max Drawdown", m.max_drawdown, targets.get("max_drawdown", 0), " USDT", 325.0),
    ]

    all_pass = True
    for name, actual, target, unit, threshold in comparisons:
        diff = actual - target
        passed = abs(diff) <= threshold
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False

        if isinstance(actual, float):
            actual_str = f"{actual:.2f}{unit}"
            diff_str = f"{diff:+.2f}"
        else:
            actual_str = f"{actual}{unit}"
            diff_str = f"{diff:+d}"

        target_str = f"{target:.2f}{unit}" if isinstance(target, float) else f"{target}{unit}"
        print(f"  {name:<22} {actual_str:>12} {target_str:>12} {diff_str:>10} {status:>8}")

    print()
    if all_pass:
        print("  VALIDATION: ALL METRICS WITHIN TOLERANCE")
    else:
        print("  VALIDATION: SOME METRICS OUTSIDE TOLERANCE")


def _print_symbol_score(score: SymbolScoreBreakdown):
    print()
    print("  SYMBOL SCORE")
    print(f"  {'-'*40}")
    print(f"  {'Expectancy (35%):':<25} {score.e_score:>10.1f}")
    print(f"  {'Stability (25%):':<25} {score.s_score:>10.1f}")
    print(f"  {'Liquidity (15%):':<25} {score.l_score:>10.1f}")
    print(f"  {'Sample Size (25%):':<25} {score.p_score:>10.1f}")
    print(f"  {'COMPOSITE:':<25} {score.composite:>10.1f} / 100")
    print(f"  {'Bracket:':<25} {score.bracket:>10}")


def _print_risk_summary(risk_engine):
    """Print risk engine events summary."""
    events = risk_engine.events
    print()
    print("  RISK ENGINE")
    print(f"  {'-'*40}")

    if not events:
        print("  No kill-switch events triggered")
        return

    disables = [e for e in events if e.event_type == 'disable']
    enables = [e for e in events if e.event_type == 'enable']
    print(f"  Disables: {len(disables)}, Re-enables: {len(enables)}")

    # Group disables by rule
    rules = {}
    for e in disables:
        rule = e.trigger_rule.split('_')[0]
        rules[rule] = rules.get(rule, 0) + 1

    for rule, count in sorted(rules.items()):
        print(f"    {rule}: {count} triggers")

    print()
    print(f"  {'Date':>20} {'Type':>8} {'Rule':<35} {'Value':>8}")
    print(f"  {'-'*20} {'-'*8} {'-'*35} {'-'*8}")
    for e in events[:15]:
        dt = datetime.fromtimestamp(e.timestamp_ms / 1000, tz=timezone.utc)
        date_str = dt.strftime("%Y-%m-%d %H:%M")
        print(f"  {date_str:>20} {e.event_type:>8} {e.trigger_rule:<35} "
              f"{e.trigger_value:>8.2f}")
    if len(events) > 15:
        print(f"  ... and {len(events) - 15} more events")
