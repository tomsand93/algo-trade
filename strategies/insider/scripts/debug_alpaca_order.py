"""
Debug Alpaca order submission to see the exact error.
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.live.alpaca_paper import AlpacaPaperClient

print("=" * 60)
print("Debug Alpaca Order Submission")
print("=" * 60)

client = AlpacaPaperClient()

# Check market hours using API directly
print(f"\nMarket Status:")
try:
    import requests
    clock_response = requests.get(
        f"{AlpacaPaperClient.PAPER_BASE_URL}/v2/clock",
        headers={
            "APCA-API-KEY-ID": client.api_key,
            "APCA-API-SECRET-KEY": client.api_secret,
        },
        timeout=30
    )
    clock = clock_response.json()
    print(f"  Timestamp: {clock.get('timestamp')}")
    print(f"  Is Open: {clock.get('is_open')}")
    print(f"  Next Open: {clock.get('next_open')}")
    print(f"  Next Close: {clock.get('next_close')}")
except Exception as e:
    print(f"  Could not get clock: {e}")

# Get account
account = client.get_account()
print(f"\nAccount:")
print(f"  Cash: ${float(account.get('cash', 0)):,.2f}")
print(f"  Buying Power: ${float(account.get('buying_power', 0)):,.2f}")

# Try a bracket order
print(f"\nAttempting bracket order for AAPL...")

try:
    from decimal import Decimal
    response = client.submit_bracket_order(
        symbol="AAPL",
        side="buy",
        qty=Decimal("1"),
        stop_loss_pct=Decimal("0.08"),
        take_profit_pct=Decimal("0.16"),
    )
    print(f"Success! Order ID: {response.get('id')}")
    print(f"Response: {response}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

# Try a simple market order without brackets
print(f"\nAttempting simple market order for AAPL...")

try:
    import requests
    from decimal import Decimal

    order_data = {
        "symbol": "AAPL",
        "side": "buy",
        "type": "market",
        "qty": 1,
        "time_in_force": "day"
    }

    response = requests.post(
        f"{AlpacaPaperClient.PAPER_BASE_URL}/v2/orders",
        headers={
            "APCA-API-KEY-ID": client.api_key,
            "APCA-API-SECRET-KEY": client.api_secret,
        },
        json=order_data,
        timeout=30
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
