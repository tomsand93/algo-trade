"""
Test signal processing directly (bypasses trading hours check).
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import yaml
from decimal import Decimal

from src.live.scheduler import PaperTradingBot

print("=" * 60)
print("Test Signal Processing (Dry Run)")
print("=" * 60)

# Load config
with open("configs/config.yaml", "r") as f:
    full_config = yaml.safe_load(f)

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
print("Fetching and Processing Signals...")
print("=" * 60)

# Fetch signals directly
signals = bot._fetch_recent_signals()

print(f"\nFound {len(signals)} signals")

if signals:
    print(f"\nTop 10 signals by value:")
    print(f"{'Ticker':<8} {'Signal Date':<12} {'Value':>15} {'Shares':>10}")
    print("-" * 50)
    for sig in sorted(signals, key=lambda s: s.buy_value_usd, reverse=True)[:10]:
        print(f"{sig.ticker:<8} {sig.signal_date.strftime('%Y-%m-%d'):<12} ${sig.buy_value_usd:>13,.0f} {sig.shares:>10.0f}")

    # Process signals
    print(f"\nProcessing signals through order_manager...")
    bot.order_manager.process_signals(signals)

    # Check what would be ordered
    status = bot.order_manager.get_status()
    print(f"\nOrder Manager Status:")
    print(f"  Managed Positions: {status['managed_positions']}")
    print(f"  Max Positions: {status['max_positions']}")
    print(f"  Processed Signals: {status['processed_signals']}")

    if status['positions']:
        print(f"\n  Positions that would be opened:")
        for p in status['positions']:
            print(f"    {p['symbol']}: {p['shares']} shares @ ${p['entry_price']}")
else:
    print("No signals found!")

print("\n" + "=" * 60)
print("Test complete! (No orders submitted - dry run mode)")
print("=" * 60)
