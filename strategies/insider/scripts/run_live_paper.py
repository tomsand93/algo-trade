"""
Run live paper trading - submits real orders to Alpaca paper trading.
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
print("LIVE PAPER TRADING")
print("=" * 60)
print("\nWARNING: This will submit REAL orders to Alpaca PAPER trading")
print("No real money is involved, but orders will be placed.\n")

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

dry_run = config.get("dry_run", True)
print(f"Config:")
print(f"  Dry Run: {dry_run}")
print(f"  Position Size: {config.get('position_size_pct', 0.10) * 100:.0f}%")
print(f"  Max Positions: {config.get('max_positions', 5)}")
print(f"  Stop Loss: {config.get('stop_loss_pct', 0.08) * 100:.0f}%")
print(f"  Take Profit: {config.get('take_profit_pct', 0.16) * 100:.0f}%")

if not dry_run:
    print("\n*** LIVE MODE - ORDERS WILL BE SUBMITTED ***")
else:
    print("\n*** DRY RUN MODE - NO ORDERS WILL BE SUBMITTED ***")

# Create bot
bot = PaperTradingBot(
    config=config,
    state_file="data/bot_state.json",
    log_file="logs/paper_trading.log",
)

print("\n" + "=" * 60)
print("Running bot iteration...")
print("=" * 60)

# Fetch and process signals (bypass trading hours check)
signals = bot._fetch_recent_signals()

print(f"\nFound {len(signals)} signals")

if signals:
    print(f"\nTop signals by value:")
    for sig in sorted(signals, key=lambda s: s.buy_value_usd, reverse=True)[:5]:
        print(f"  {sig.ticker}: {sig.signal_date} - ${sig.buy_value_usd:,.0f}")

    # Process signals
    print(f"\nProcessing signals...")
    bot.order_manager.process_signals(signals)

    # Get status
    status = bot.order_manager.get_status()
    print(f"\nOrder Manager Status:")
    print(f"  Managed Positions: {status['managed_positions']}/{status['max_positions']}")
    print(f"  Processed Signals: {status['processed_signals']}")

    if status['positions']:
        print(f"\nPositions:")
        for p in status['positions']:
            print(f"  {p['symbol']}: {p['shares']} shares @ ${p['entry_price']}")
            print(f"    Stop: ${p['stop_loss']} | Take: ${p['take_profit']}")

# Save state
bot._save_state()

# Check Alpaca account
print(f"\n" + "=" * 60)
print("Alpaca Account Status:")
print("=" * 60)
account = bot.client.get_account()
print(f"  Cash: ${float(account.get('cash', 0)):,.2f}")
print(f"  Portfolio Value: ${float(account.get('portfolio_value', 0)):,.2f}")
print(f"  Buying Power: ${float(account.get('buying_power', 0)):,.2f}")

positions = bot.client.get_positions()
print(f"  Open Positions: {len(positions)}")
for pos in positions:
    print(f"    {pos.symbol}: {pos.qty} shares @ ${pos.avg_entry_price}")

print("\n" + "=" * 60)
print("Iteration complete!")
print("=" * 60)
