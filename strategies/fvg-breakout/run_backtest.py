"""Active backtest entry point for the FVG breakout strategy."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Iterable

from src.analytics import (
    PerformanceAnalyzer,
    plot_equity_curve,
    plot_r_multiple_distribution,
)
from src.backtest_engine import BacktestEngine
from src.config import BACKTEST_CONFIG, STRATEGY_CONFIG
from src.data_fetcher import get_data


def print_strategy_explanation() -> None:
    """Print the rule set and execution model."""
    print("=" * 68)
    print("FVG BREAKOUT STRATEGY")
    print("=" * 68)
    print("Rules:")
    print("1. Capture the 09:30-09:35 ET candle high and low.")
    print("2. Wait for a break above the high or below the low.")
    print("3. Detect a 3-candle Fair Value Gap after the break.")
    print("4. Require a retest into the gap.")
    print("5. Require an immediate engulfing confirmation candle.")
    print("6. Use fixed 3:1 reward-to-risk exits.")
    print()
    print("Hard limits:")
    print("- Maximum 1 trade per symbol per day")
    print("- No trades before 09:35 ET")
    print("- No averaging or discretionary overrides")
    print("=" * 68)


def progress_callback(current: int, total: int, symbol: str) -> None:
    """Print simple progress updates during the run."""
    print(f"[{current + 1}/{total}] Processing {symbol}")


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Run the FVG breakout strategy backtest.",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Symbols to backtest. Defaults to the configured symbol list.",
    )
    parser.add_argument(
        "--start-date",
        default=BACKTEST_CONFIG.start_date,
        help="Backtest start date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--end-date",
        default=BACKTEST_CONFIG.end_date,
        help="Backtest end date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=100000.0,
        help="Initial capital for the simulation.",
    )
    parser.add_argument(
        "--use-csv",
        action="store_true",
        help="Load data from CSV files instead of Alpaca or cached parquet files.",
    )
    parser.add_argument(
        "--csv-dir",
        default="csv_data",
        help="Directory containing SYMBOL_1Min.csv and SYMBOL_5Min.csv files.",
    )
    parser.add_argument(
        "--cache-dir",
        default="data",
        help="Directory used for cached parquet data.",
    )
    parser.add_argument(
        "--output-dir",
        default="results",
        help="Directory for generated reports and plots.",
    )
    parser.add_argument(
        "--skip-plots",
        action="store_true",
        help="Skip PNG output generation.",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Print the strategy explanation and exit.",
    )
    return parser


def resolve_symbols(symbols: Iterable[str] | None) -> list[str]:
    """Return user-provided symbols or the configured defaults."""
    if symbols:
        return list(symbols)
    return list(STRATEGY_CONFIG.symbols)


def run_backtest(args: argparse.Namespace) -> int:
    """Execute the backtest and save outputs."""
    symbols = resolve_symbols(args.symbols)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    data = get_data(
        symbols=symbols,
        start_date=args.start_date,
        end_date=args.end_date,
        use_cache=not args.use_csv,
        cache_dir=args.cache_dir,
        use_csv=args.use_csv,
        csv_dir=args.csv_dir,
        validate=True,
    )

    engine = BacktestEngine(initial_capital=args.capital)
    result = engine.run_backtest(data, progress_callback=progress_callback)
    analyzer = PerformanceAnalyzer(result)
    analyzer.print_report()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    trades_path = output_dir / f"trades_{timestamp}.csv"
    report_path = output_dir / f"report_{timestamp}.json"

    analyzer.save_trades_csv(str(trades_path))
    analyzer.save_report_json(str(report_path))

    if not args.skip_plots:
        equity_path = output_dir / f"equity_curve_{timestamp}.png"
        r_dist_path = output_dir / f"r_distribution_{timestamp}.png"
        plot_equity_curve(result, save_path=str(equity_path))
        plot_r_multiple_distribution(result, save_path=str(r_dist_path))

    print(f"Outputs written to {output_dir}")
    return 0


def main() -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.explain:
        print_strategy_explanation()
        return 0

    return run_backtest(args)


if __name__ == "__main__":
    raise SystemExit(main())
