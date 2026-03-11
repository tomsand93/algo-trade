"""
Check Alpaca orders and positions.
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import requests

api_key = os.getenv("ALPACA_API_KEY")
api_secret = os.getenv("ALPACA_API_SECRET")
base_url = "https://paper-api.alpaca.markets"

print("=" * 60)
print("Alpaca Orders & Positions")
print("=" * 60)

# Check positions
print("\nPositions:")
response = requests.get(
    f"{base_url}/v2/positions",
    headers={
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    },
    timeout=30
)

if response.status_code == 200:
    positions = response.json()
    print(f"  Count: {len(positions)}")
    for pos in positions:
        print(f"  {pos.get('symbol')}: {pos.get('qty')} shares @ ${pos.get('avg_entry_price')}")
else:
    print(f"  Error: {response.status_code}")

# Check orders
print("\nOrders:")
response = requests.get(
    f"{base_url}/v2/orders?status=all",
    headers={
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    },
    timeout=30
)

if response.status_code == 200:
    orders = response.json()
    print(f"  Count: {len(orders)}")
    for order in orders[:10]:  # Show first 10
        print(f"  {order.get('symbol')}: {order.get('side')} {order.get('qty')} shares")
        print(f"    Status: {order.get('status')}, Type: {order.get('order_class')}")
        if order.get('order_class') == 'bracket':
            stop = order.get('stop_loss', {})
            take = order.get('take_profit', {})
            print(f"    Stop: ${stop.get('stop_price', 'N/A')}, Take: ${take.get('limit_price', 'N/A')}")
else:
    print(f"  Error: {response.status_code}")

# Check account
print("\nAccount:")
response = requests.get(
    f"{base_url}/v2/account",
    headers={
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    },
    timeout=30
)

if response.status_code == 200:
    account = response.json()
    print(f"  Cash: ${float(account.get('cash', 0)):,.2f}")
    print(f"  Portfolio Value: ${float(account.get('portfolio_value', 0)):,.2f}")
    print(f"  Buying Power: ${float(account.get('buying_power', 0)):,.2f}")
