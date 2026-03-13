"""
Multi-symbol US stock backtest runner for BDB DCA strategy.

Fetches 30m stock bars from Alpaca, runs the BDB DCA backtest per symbol,
and prints a ranked comparison table.

CLI flags:
  --symbols AAPL,MSFT,SPY   Override default symbol list
  --start 2023-01-01         Override start date
  --stop 2025-01-01          Override stop date
  --sl 999                   Stop loss ATR multiplier (default 999 = disabled)
  --tp 2.0                   Take profit ATR multiplier (default 2.0)
  --report                   Print full extended report per symbol
  --csv                      Export per-symbol trade CSVs
"""

import sys
from dataclasses import replace
from datetime import datetime, timezone

from bdb_dca.config import StrategyConfig
from bdb_dca.stock_data_fetcher import fetch_stock_bars
from bdb_dca.stock_backtest import run_stock_backtest
from bdb_dca.models import BacktestResult
from bdb_dca.metrics import compute_extended_metrics
from bdb_dca.reporting import print_full_report, export_trades_csv

DEFAULT_SYMBOLS = [
    # Tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
    # ETFs
    "SPY", "QQQ", "IWM", "DIA",
    # Financials
    "JPM", "BAC",
    # Other
    "XOM", "JNJ", "WMT", "HD",
    # High-beta
    "AMD", "NFLX", "COIN",
]

# Stock-specific config overrides
STOCK_START = "2023-01-01"
STOCK_STOP = "2025-01-01"
STOCK_WARMUP = "2022-10-01"
STOCK_COMMISSION_PCT = 0.10
STOCK_TICK_SIZE = 0.01
STOCK_SLIPPAGE_TICKS = 2


def parse_args():
    """Parse CLI arguments."""
    symbols = DEFAULT_SYMBOLS
    start = STOCK_START
    stop = STOCK_STOP
    sl_mult = 999.0  # effectively disabled - SL hurts DCA strategy
    tp_mult = 2.0    # original optimal value
    full_report = "--report" in sys.argv
    export_csv = "--csv" in sys.argv

    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--symbols" and i + 1 < len(sys.argv):
            symbols = [s.strip().upper() for s in sys.argv[i + 1].split(",") if s.strip()]
        elif arg == "--start" and i + 1 < len(sys.argv):
            start = sys.argv[i + 1]
        elif arg == "--stop" and i + 1 < len(sys.argv):
            stop = sys.argv[i + 1]
        elif arg == "--sl" and i + 1 < len(sys.argv):
            sl_mult = float(sys.argv[i + 1])
        elif arg == "--tp" and i + 1 < len(sys.argv):
            tp_mult = float(sys.argv[i + 1])

    return symbols, start, stop, sl_mult, tp_mult, full_report, export_csv


def make_stock_config(symbol: str, start: str, stop: str) -> StrategyConfig:
    """Create a StrategyConfig with stock-specific overrides."""
    warmup_start = STOCK_WARMUP
    # If user overrides start, push warmup back 3 months
    if start != STOCK_START:
        dt = datetime.strptime(start, "%Y-%m-%d")
        warmup_dt = dt.replace(month=dt.month - 3) if dt.month > 3 else dt.replace(
            year=dt.year - 1, month=dt.month + 9
        )
        warmup_start = warmup_dt.strftime("%Y-%m-%d")

    return StrategyConfig(
        symbol=symbol,
        start_date=start,
        stop_date=stop,
        warmup_start=warmup_start,
        commission_pct=STOCK_COMMISSION_PCT,
        tick_size=STOCK_TICK_SIZE,
        slippage_ticks=STOCK_SLIPPAGE_TICKS,
    )


def run_single_symbol(symbol: str, config: StrategyConfig,
                      sl_mult: float, tp_mult: float,
                      full_report: bool, export_csv: bool) -> dict:
    """Run backtest for a single symbol, return summary dict."""
    try:
        bars = fetch_stock_bars(
            symbol=symbol,
            start_date=config.warmup_start,
            end_date=config.stop_date,
        )
    except Exception as e:
        print(f"  ERROR fetching {symbol}: {e}")
        return {"symbol": symbol, "error": str(e)}

    print(f"  {symbol}: {len(bars)} bars loaded")

    result = run_stock_backtest(bars, config,
                                stoploss_atr_mult=sl_mult,
                                takeprofit_atr_mult=tp_mult)
    metrics = compute_extended_metrics(result)

    if full_report:
        print()
        print(f"  === {symbol} FULL REPORT ===")
        print_full_report(result, bars=bars)

    if export_csv:
        csv_path = f"data/{symbol}_stock_trades.csv"
        export_trades_csv(result, csv_path)

    sl_exits = getattr(result, 'sl_exits', 0)

    return {
        "symbol": symbol,
        "net_pct": metrics.net_profit_pct,
        "win_rate": metrics.win_rate,
        "trades": metrics.total_trades,
        "pf": metrics.profit_factor,
        "sharpe": metrics.sharpe_ratio,
        "max_dd": metrics.max_drawdown,
        "net_profit": metrics.net_profit,
        "avg_trade": metrics.avg_trade_pnl,
        "sl_exits": sl_exits,
    }


def print_comparison_table(results: list[dict]):
    """Print ranked comparison table sorted by net profit %."""
    # Filter out errors
    valid = [r for r in results if "error" not in r]
    errors = [r for r in results if "error" in r]

    if not valid:
        print("\nNo valid results to display.")
        return

    # Sort by net profit % descending
    valid.sort(key=lambda r: r["net_pct"], reverse=True)

    print()
    print("=" * 100)
    print("  STOCK BACKTEST COMPARISON — with Stop Loss (ranked by Net Profit %)")
    print("=" * 100)
    print()

    header = (
        f"  {'#':>3} {'Symbol':<8} {'Net %':>8} {'Net $':>10} "
        f"{'Trades':>7} {'SL':>4} {'Win%':>7} {'PF':>7} {'Sharpe':>8} "
        f"{'MaxDD':>10} {'Avg/Trd':>9}"
    )
    print(header)
    print(f"  {'---':>3} {'--------':<8} {'--------':>8} {'----------':>10} "
          f"{'-------':>7} {'----':>4} {'-------':>7} {'-------':>7} {'--------':>8} "
          f"{'----------':>10} {'---------':>9}")

    for i, r in enumerate(valid, 1):
        pf_str = f"{r['pf']:.2f}" if r['pf'] < 1000 else "inf"
        print(
            f"  {i:>3} {r['symbol']:<8} {r['net_pct']:>+7.2f}% "
            f"{r['net_profit']:>10.2f} {r['trades']:>7} "
            f"{r.get('sl_exits', 0):>4} "
            f"{r['win_rate']:>6.1f}% {pf_str:>7} {r['sharpe']:>8.2f} "
            f"{r['max_dd']:>10.2f} {r['avg_trade']:>9.2f}"
        )

    if errors:
        print()
        print("  ERRORS:")
        for r in errors:
            print(f"    {r['symbol']}: {r['error']}")

    # Summary stats
    print()
    print("-" * 95)
    profitable = [r for r in valid if r["net_pct"] > 0]
    unprofitable = [r for r in valid if r["net_pct"] <= 0]
    avg_return = sum(r["net_pct"] for r in valid) / len(valid)
    best = valid[0]
    worst = valid[-1]

    print(f"  Symbols tested:   {len(valid)}")
    print(f"  Profitable:       {len(profitable)} / {len(valid)} "
          f"({len(profitable)/len(valid)*100:.0f}%)")
    print(f"  Unprofitable:     {len(unprofitable)}")
    print(f"  Average return:   {avg_return:+.2f}%")
    print(f"  Best:             {best['symbol']} ({best['net_pct']:+.2f}%)")
    print(f"  Worst:            {worst['symbol']} ({worst['net_pct']:+.2f}%)")

    total_trades = sum(r["trades"] for r in valid)
    avg_trades = total_trades / len(valid)
    print(f"  Total trades:     {total_trades}")
    print(f"  Avg trades/symbol:{avg_trades:.1f}")
    print()


def main():
    symbols, start, stop, sl_mult, tp_mult, full_report, export_csv = parse_args()

    print()
    print("BDB DCA Stock Backtest (with Stop Loss)")
    print("=" * 50)
    print(f"Symbols:   {len(symbols)} ({', '.join(symbols[:5])}{'...' if len(symbols) > 5 else ''})")
    print(f"Period:    {start} to {stop}")
    print(f"SL:        {sl_mult}x ATR   TP: {tp_mult}x ATR")
    print(f"Commission:{STOCK_COMMISSION_PCT}%  Slippage: {STOCK_SLIPPAGE_TICKS} x ${STOCK_TICK_SIZE}")
    print(f"Report:    {'full' if full_report else 'summary'}  CSV: {'yes' if export_csv else 'no'}")
    print()

    results = []
    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] {symbol}")
        config = make_stock_config(symbol, start, stop)
        summary = run_single_symbol(symbol, config, sl_mult, tp_mult,
                                    full_report, export_csv)
        results.append(summary)

    print_comparison_table(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
