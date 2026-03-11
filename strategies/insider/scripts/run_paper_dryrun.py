"""
Run paper trading bot in dry-run mode (single iteration).
This tests signal fetching and order logic without submitting real orders.
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import yaml
from decimal import Decimal
from datetime import date

from src.live.scheduler import PaperTradingBot

print("=" * 60)
print("Insider Trading Bot - Dry Run Test")
print("=" * 60)

# Load config
with open("configs/config.yaml", "r") as f:
    full_config = yaml.safe_load(f)

# Merge paper_trading config with main config
config = {
    **full_config.get("paper_trading", {}),
    **{
        "threshold_usd": full_config.get("strategy", {}).get("threshold_usd", 100000),
        "min_dvol": full_config.get("strategy", {}).get("min_dvol"),
        "price_provider": full_config.get("data", {}).get("price_provider", "yfinance"),
        "cache_path": "data/insider_multi_ticker.json",
    },
    **full_config.get("risk", {})
}

print(f"\nConfig:")
print(f"  Position Size: {config.get('position_size_pct', 0.10) * 100:.0f}%")
print(f"  Max Positions: {config.get('max_positions', 5)}")
print(f"  Stop Loss: {config.get('stop_loss_pct', 0.08) * 100:.0f}%")
print(f"  Take Profit: {config.get('take_profit_pct', 0.16) * 100:.0f}%")
print(f"  Dry Run: {config.get('dry_run', True)}")
print(f"  Threshold: ${config.get('threshold_usd', 100000):,.0f}")

# Create bot
bot = PaperTradingBot(
    config=config,
    state_file="data/bot_state.json",
    log_file="logs/paper_dryrun.log",
)

print("\n" + "=" * 60)
print("Running single iteration (dry run)...")
print("=" * 60)

# Run once
status = bot.run_once()

print("\n" + "=" * 60)
print("Results:")
print("=" * 60)
print(f"  Managed Positions: {status['order_manager']['managed_positions']}")
print(f"  Processed Signals: {status['order_manager']['processed_signals']}")
print(f"  Dry Run: {status['order_manager']['dry_run']}")

if status['order_manager']['positions']:
    print("\n  Current Positions:")
    for p in status['order_manager']['positions']:
        print(f"    {p['symbol']}: {p['shares']} shares @ ${p['entry_price']}")

print("\n" + "=" * 60)
print("Dry run complete. No orders were submitted.")
print("=" * 60)
