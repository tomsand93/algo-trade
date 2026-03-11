#!/usr/bin/env python3
"""
Run paper trading bot.

WARNING: This bot places REAL orders on Alpaca paper trading.
Always verify PAPER_MODE=true in .env before running.

Usage:
    python scripts/run_paper.py --config configs/config.yaml

Dry run (log only, no orders):
    python scripts/run_paper.py --config configs/config.yaml --dry-run

Single run (for testing):
    python scripts/run_paper.py --config configs/config.yaml --once
"""
import argparse
import logging
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.live.scheduler import PaperTradingBot
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run paper trading bot"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/config.yaml",
        help="Path to config file"
    )
    parser.add_argument(
        "--env",
        type=str,
        default=".env",
        help="Path to .env file"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log orders without submitting"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run single iteration and exit"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Seconds between runs (default: 300)"
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Maximum iterations (for testing)"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Load environment variables
    env_path = Path(args.env)
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f"Loaded environment from {env_path}")
    else:
        logger.warning(f".env file not found: {env_path}")

    # Check paper mode
    paper_mode = os.getenv("PAPER_MODE", "").lower() in ("true", "1", "yes")
    if not paper_mode:
        logger.error(
            "PAPER_MODE not set to 'true'. "
            "For safety, set PAPER_MODE=true in your .env file."
        )
        return 1

    # Check Alpaca credentials
    api_key = os.getenv("ALPACA_API_KEY")
    api_secret = os.getenv("ALPACA_API_SECRET")
    if not api_key or not api_secret:
        logger.error(
            "Alpaca credentials not found. "
            "Set ALPACA_API_KEY and ALPACA_API_SECRET in your .env file."
        )
        return 1

    logger.info("=" * 60)
    logger.info("INSIDER TRADING PAPER TRADING BOT")
    logger.info("=" * 60)
    logger.info(f"Paper Mode: {paper_mode}")
    logger.info(f"Dry Run: {args.dry_run}")
    logger.info(f"Run Once: {args.once}")

    # Load config
    import yaml
    config_path = Path(args.config)
    if config_path.exists():
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    else:
        logger.warning(f"Config file not found: {config_path}")
        config = {}

    # Extract paper trading config
    paper_config = config.get("paper_trading", {})
    backtest_config = config.get("backtest", {})
    risk_config = config.get("risk", {})

    # Build full config
    bot_config = {
        # Strategy
        "threshold_usd": config.get("strategy", {}).get("threshold_usd", 100000),
        "min_dvol": config.get("strategy", {}).get("min_dvol"),
        # Position sizing
        "position_size_pct": paper_config.get("position_size_pct", backtest_config.get("position_size_pct", 0.10)),
        "max_positions": paper_config.get("max_positions", backtest_config.get("max_positions", 5)),
        # Exit rules
        "stop_loss_pct": paper_config.get("stop_loss_pct", backtest_config.get("stop_loss_pct", 0.08)),
        "take_profit_pct": paper_config.get("take_profit_pct", backtest_config.get("take_profit_pct", 0.16)),
        "max_hold_bars": paper_config.get("max_hold_bars", backtest_config.get("max_hold_bars", 60)),
        # Risk
        "max_position_size_pct": risk_config.get("max_position_size_pct", 0.15),
        "max_total_exposure_pct": risk_config.get("max_total_exposure_pct", 0.95),
        "daily_loss_limit_pct": risk_config.get("daily_loss_limit_pct"),
        "max_drawdown_pct": risk_config.get("max_drawdown_pct"),
        # Other
        "dry_run": args.dry_run or paper_config.get("dry_run", False),
        "price_provider": config.get("data", {}).get("price_provider", "yfinance"),
        # Paths
        "state_file": paper_config.get("state_file", "data/bot_state.json"),
        "log_file": paper_config.get("log_file", "logs/paper_trading.log"),
    }

    # Create bot
    try:
        bot = PaperTradingBot(
            config=bot_config,
            state_file=bot_config["state_file"],
            log_file=bot_config["log_file"],
        )

        if args.once:
            # Single run
            logger.info("Running single iteration...")
            status = bot.run_once()
            logger.info(f"Status: {status}")
            return 0
        else:
            # Continuous run
            logger.info(f"Starting continuous run (interval: {args.interval}s)")
            logger.info("Press Ctrl+C to stop")
            bot.run(
                interval_seconds=args.interval,
                max_iterations=args.max_iterations,
            )
            return 0

    except KeyboardInterrupt:
        logger.info("Stopped by user")
        return 0
    except Exception as e:
        logger.error(f"Bot failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
