"""
CLI entry point for BDB DCA Backtest.

Fetches data, runs backtest, prints metrics vs Pine Script targets.
Use --risk flag to enable the risk engine.
Use --report flag for full extended report.
Use --csv flag to export trades and equity curve to CSV.
"""

import sys
from datetime import datetime, timezone

from bdb_dca.config import StrategyConfig
from bdb_dca.data_fetcher import fetch_ohlcv
from bdb_dca.backtest import run_backtest
from bdb_dca.risk import RiskConfig
from bdb_dca.reporting import print_full_report, print_trade_list, export_trades_csv, export_equity_csv


# Pine Script target metrics for validation
PINE_TARGETS = {
    "total_trades": 121,
    "win_rate": 82.64,
    "net_profit": 934.08,
    "net_profit_pct": 9.34,
    "profit_factor": 2.948,
    "max_drawdown": 624.72,
}


def main():
    config = StrategyConfig()
    use_risk = "--risk" in sys.argv
    full_report = "--report" in sys.argv
    export_csv = "--csv" in sys.argv

    # Fetch data with warmup buffer
    print(f"Symbol: {config.symbol}")
    print(f"Timeframe: {config.timeframe}")
    print(f"Trading window: {config.start_date} to {config.stop_date}")
    print(f"Warmup from: {config.warmup_start}")
    print(f"Risk engine: {'ENABLED' if use_risk else 'disabled'}")
    print()

    bars = fetch_ohlcv(
        symbol=config.symbol,
        timeframe=config.timeframe,
        start_date=config.warmup_start,
        end_date="2026-02-01",
    )
    print(f"Total bars loaded: {len(bars)}")

    # Find trading window bars for info
    start_ms = _date_to_ms(config.start_date)
    stop_ms = _date_to_ms(config.stop_date)
    trading_bars = [b for b in bars if start_ms <= b.timestamp <= stop_ms]
    print(f"Bars in trading window: {len(trading_bars)}")
    print()

    # Run backtest
    risk_config = RiskConfig() if use_risk else None
    print("Running backtest...")
    result = run_backtest(bars, config, risk_config)

    # Get risk engine from result
    risk_engine = getattr(result, 'risk_engine', None)

    if full_report:
        # Full extended report
        print_full_report(
            result,
            pine_targets=PINE_TARGETS,
            risk_engine=risk_engine,
            bars=bars,
        )
        print_trade_list(result, max_trades=10)
    else:
        # Basic comparison report (original behavior)
        _print_basic_results(result, use_risk, risk_engine)

    # CSV export
    if export_csv:
        export_trades_csv(result, "data/trades.csv")
        export_equity_csv(result, "data/equity_curve.csv")

    return 0


def _print_basic_results(result, use_risk, risk_engine):
    """Original compact results output."""
    print()
    print("=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)
    print()

    metrics = [
        ("Total Trades", result.total_trades, PINE_TARGETS["total_trades"], "", 3),
        ("Win Rate", result.win_rate, PINE_TARGETS["win_rate"], "%", 1.0),
        ("Net Profit", result.net_profit, PINE_TARGETS["net_profit"], " USDT", 19.0),
        ("Net Profit %", result.net_profit_pct, PINE_TARGETS["net_profit_pct"], "%", 0.5),
        ("Profit Factor", result.profit_factor, PINE_TARGETS["profit_factor"], "", 0.1),
        ("Max Drawdown", result.max_drawdown, PINE_TARGETS["max_drawdown"], " USDT", 325.0),
    ]

    print(f"  {'Metric':<20} {'Result':>12} {'Target':>12} {'Diff':>10} {'Pass':>6}")
    print(f"  {'-'*20} {'-'*12} {'-'*12} {'-'*10} {'-'*6}")

    all_pass = True
    for name, actual, target, unit, threshold in metrics:
        diff = actual - target
        passed = abs(diff) <= threshold
        status = "OK" if passed else "FAIL"
        if not passed:
            all_pass = False

        if isinstance(actual, float):
            actual_str = f"{actual:.2f}{unit}"
            diff_str = f"{diff:+.2f}"
        else:
            actual_str = f"{actual}{unit}"
            diff_str = f"{diff:+d}"

        target_str = f"{target}{unit}" if not isinstance(target, float) else f"{target:.2f}{unit}"
        print(f"  {name:<20} {actual_str:>12} {target_str:>12} {diff_str:>10} {status:>6}")

    print()
    print(f"  Winning trades: {result.winning_trades}")
    print(f"  Losing trades:  {result.losing_trades}")
    print(f"  Avg trade PnL:  {result.avg_trade_pnl:.2f} USDT")
    print(f"  Final equity:   {result.final_equity:.2f} USDT")
    print(f"  Closed-trade DD:{result.closed_trade_max_drawdown:.2f} USDT")
    print()

    # Risk engine summary
    if use_risk and risk_engine:
        from bdb_dca.reporting import _print_risk_summary
        _print_risk_summary(risk_engine)

    if all_pass:
        print("  VALIDATION: ALL METRICS WITHIN TOLERANCE")
    else:
        print("  VALIDATION: SOME METRICS OUTSIDE TOLERANCE")
        if not use_risk:
            print()
            _print_debug_trades(result)


def _print_debug_trades(result):
    """Print first 5 trades for debugging when validation fails."""
    print("  First 5 trades for debugging:")
    print(f"  {'#':>3} {'Entry':>8} {'EntryPx':>12} {'Exit':>8} {'ExitPx':>12} {'Qty':>10} {'PnL':>10}")
    print(f"  {'-'*3} {'-'*8} {'-'*12} {'-'*8} {'-'*12} {'-'*10} {'-'*10}")
    for i, t in enumerate(result.trades[:5]):
        print(f"  {i+1:>3} {t.entry_bar_index:>8} {t.entry_price:>12.2f} "
              f"{t.exit_bar_index:>8} {t.exit_price:>12.2f} "
              f"{t.entry_qty:>10.6f} {t.pnl_net:>10.2f}")


def _date_to_ms(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


if __name__ == "__main__":
    sys.exit(main())
