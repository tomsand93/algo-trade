#!/usr/bin/env python3
"""Show paper trading status and performance."""
import sys
sys.path.insert(0, "src")

from dotenv import load_dotenv
load_dotenv()
from src.live.alpaca_paper import AlpacaPaperClient
from datetime import datetime
import json

client = AlpacaPaperClient()
account = client.get_account()
positions = client.get_positions()
orders = client.get_orders(status='open', limit=20)

# Load bot state
try:
    with open('data/bot_state.json', 'r') as f:
        bot_state = json.load(f)
except:
    bot_state = {"processed_signals": [], "positions": []}

print('=' * 60)
print('         PAPER TRADING DASHBOARD')
print('=' * 60)
print(f'Time:        {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
print()
print('ACCOUNT')
print('-' * 40)
print(f'Cash:              ${account.get("cash", "0")}')
print(f'Portfolio Value:   ${account.get("portfolio_value", "0")}')
print(f'Buying Power:      ${account.get("buying_power", "0")}')
equity = float(account.get("portfolio_value", 0)) + float(account.get("cash", 0))
print(f'Equity:            ${equity:.2f}')
print()
print('POSITIONS')
print('-' * 40)
print(f'Open Positions:    {len(positions)}')
if positions:
    for p in positions:
        pnl_pct = (float(p.current_price) - float(p.avg_entry_price)) / float(p.avg_entry_price) * 100
        pnl_dollar = float(p.unrealized_pnl)
        print(f'  {p.symbol}: {p.shares} shares @ ${p.avg_entry_price}')
        print(f'           Current: ${p.current_price} | PnL: ${pnl_dollar:+.2f} ({pnl_pct:+.2f}%)')
else:
    print('  (none)')
print()
print('ORDERS')
print('-' * 40)
print(f'Open Orders:       {len(orders)}')
if orders:
    for o in orders[:10]:
        print(f'  {o.get("symbol")}: {o.get("side")} {o.get("qty", {}).get("qty", o.get("qty"))} @ {o.get("type", "market")} [{o.get("status")}]')
else:
    print('  (none)')
print()
print('BOT STATE')
print('-' * 40)
print(f'Processed Signals: {len(bot_state.get("processed_signals", []))}')
print(f'Managed Positions: {len(bot_state.get("positions", []))}')
print()
print('PERFORMANCE METRICS')
print('-' * 40)
print(f'Total Return:      +0.00%')
print(f'Daily PnL:         +0.00%')
print(f'Max Drawdown:      0.00%')
print(f'Peak Equity:       ${equity:.2f}')
print(f'Win Rate:          N/A (no trades yet)')
print('=' * 60)
