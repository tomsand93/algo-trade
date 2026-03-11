#!/usr/bin/env python3
"""
Run backtest for insider trading strategy.

Usage:
    python scripts/run_backtest.py --data data/insider_transactions.json --start 2024-01-01 --end 2024-12-31

With custom parameters:
    python scripts/run_backtest.py --data data/insider_transactions.json --start 2024-01-01 --end 2024-12-31 --threshold 50000 --stop 0.10 --take 0.20

Parameter sweep:
    python scripts/run_backtest.py --sweep --data data/insider_transactions.json --start 2024-01-01 --end 2024-12-31
"""
import argparse
import json
import logging
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.signals.single_buy_threshold import load_transactions_and_generate_signals
from src.backtest.engine import BacktestEngine
from src.data.price_provider import get_price_provider
from src.reports import metrics as metrics_module
from src.reports.run_report import generate_report, print_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run backtest for insider trading strategy"
    )
    parser.add_argument(
        "--data",
        type=str,
        required=True,
        help="Path to insider transactions JSON file"
    )
    parser.add_argument(
        "--start",
        type=str,
        required=True,
        help="Backtest start date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end",
        type=str,
        required=True,
        help="Backtest end date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/config.yaml",
        help="Path to config file"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="results/backtest",
        help="Output directory for results"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Override threshold USD"
    )
    parser.add_argument(
        "--stop",
        type=float,
        default=None,
        help="Override stop loss percentage"
    )
    parser.add_argument(
        "--take",
        type=float,
        default=None,
        help="Override take profit percentage"
    )
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Run parameter sweep instead of single backtest"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick sweep with smaller parameter grid"
    )
    return parser.parse_args()


def run_single_backtest(args, config):
    """Run a single backtest with specified parameters."""
    # Load config or defaults
    backtest_config = config.get("backtest", {})

    # Override with command line args
    threshold = args.threshold if args.threshold is not None else backtest_config.get("threshold_usd", 100000)
    stop_loss = args.stop if args.stop is not None else backtest_config.get("stop_loss_pct", 0.08)
    take_profit = args.take if args.take is not None else backtest_config.get("take_profit_pct", 0.16)

    logger.info(f"Backtest parameters: threshold=${threshold}, stop={stop_loss*100}%, take={take_profit*100}%")

    # Generate signals
    logger.info("Generating signals...")
    signals = load_transactions_and_generate_signals(
        data_path=args.data,
        source=config.get("data", {}).get("insider_source", "secapi"),
        threshold_usd=Decimal(str(threshold)),
        min_dvol=Decimal(str(backtest_config.get("min_dvol", 5000000))) if backtest_config.get("min_dvol") else None,
    )

    if not signals:
        logger.warning("No signals generated!")
        return

    logger.info(f"Generated {len(signals)} signals")

    # Parse dates
    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)

    # Create price provider
    price_provider = get_price_provider(
        provider=config.get("data", {}).get("price_provider", "yfinance")
    )

    # Create backtest engine
    engine = BacktestEngine(
        initial_cash=Decimal(str(backtest_config.get("initial_cash", 100000))),
        position_size_pct=Decimal(str(backtest_config.get("position_size_pct", 0.10))),
        max_positions=backtest_config.get("max_positions", 5),
        max_daily_new_positions=backtest_config.get("max_daily_new_positions", 3),
        stop_loss_pct=Decimal(str(stop_loss)),
        take_profit_pct=Decimal(str(take_profit)),
        hold_bars=None,  # Use bracket exits
        max_hold_bars=backtest_config.get("max_hold_bars", 60),
        commission_per_share=Decimal(str(backtest_config.get("commission_per_share", 0.005))),
        min_commission=Decimal(str(backtest_config.get("min_commission", 1.0))),
        slippage_bps=Decimal(str(backtest_config.get("slippage_bps", 2))),
        fill_assumption=backtest_config.get("fill_assumption", "worst"),
        timeframe=backtest_config.get("timeframe", "1D"),
        price_provider=price_provider,
    )

    # Run backtest
    logger.info(f"Running backtest from {start_date} to {end_date}...")
    results = engine.run(signals, start_date, end_date)

    # Print summary
    print_summary(results)

    # Generate report
    output_dir = args.output
    generate_report(
        backtest_results=results,
        trades=engine.trades,
        output_dir=output_dir,
    )

    # Save JSON results
    results_path = Path(output_dir) / "results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    logger.info(f"Results saved to {output_dir}")


def run_parameter_sweep(args, config):
    """Run parameter sweep over multiple combinations."""
    # Load config
    sweep_config = config.get("parameter_sweep", {})
    backtest_config = config.get("backtest", {})

    # Use quick sweep if requested
    if args.quick:
        logger.info("Using quick parameter grid")
        parameter_grid = {
            "threshold_usd": [100000],
            "stop_loss_pct": [0.08],
            "take_profit_pct": [0.08, 0.10, 0.12, 0.14, 0.16, 0.18, 0.20],
        }
    else:
        parameter_grid = {
            "threshold_usd": sweep_config.get("threshold_usd", [25000, 50000, 100000, 250000, 500000]),
            "stop_loss_pct": sweep_config.get("stop_loss_pct", [0.05, 0.08, 0.10]),
            "take_profit_pct": sweep_config.get("take_profit_pct", [0.10, 0.16, 0.20]),
        }

    logger.info(f"Parameter grid: {parameter_grid}")

    # Generate signals once
    logger.info("Generating signals...")
    signals = load_transactions_and_generate_signals(
        data_path=args.data,
        source=config.get("data", {}).get("insider_source", "secapi"),
        threshold_usd=Decimal("25000"),  # Use lowest threshold for sweep
        min_dvol=Decimal(str(backtest_config.get("min_dvol", 5000000))) if backtest_config.get("min_dvol") else None,
    )

    if not signals:
        logger.warning("No signals generated!")
        return

    logger.info(f"Generated {len(signals)} signals for sweep")

    # Parse dates
    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)

    # Create price provider
    price_provider = get_price_provider(
        provider=config.get("data", {}).get("price_provider", "yfinance")
    )

    # Run sweep
    logger.info("Running parameter sweep...")
    results_df = metrics_module.run_parameter_sweep(
        signals=signals,
        start_date=start_date,
        end_date=end_date,
        price_provider=price_provider,
        parameter_grid=parameter_grid,
    )

    # Save results table
    output_path = Path(args.output) / "sweep_results.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metrics_module.create_results_table(results_df, str(output_path))

    # Print top results
    print("\n" + "=" * 80)
    print("PARAMETER SWEEP RESULTS (Top 10 by CAGR)")
    print("=" * 80)
    print(results_df.head(10).to_string(index=False))
    print("=" * 80)

    logger.info(f"Sweep results saved to {output_path}")


def main():
    args = parse_args()

    # Load config
    import yaml
    config_path = Path(args.config)
    if config_path.exists():
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    else:
        logger.warning(f"Config file not found: {config_path}")
        config = {}

    try:
        if args.sweep:
            run_parameter_sweep(args, config)
        else:
            run_single_backtest(args, config)
        return 0
    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
