"""
Debug bracket order error - get actual error message.
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import requests
from decimal import Decimal

api_key = os.getenv("ALPACA_API_KEY")
api_secret = os.getenv("ALPACA_API_SECRET")

base_url = "https://paper-api.alpaca.markets"

# Get AAPL price
print("Getting AAPL price...")
quote_response = requests.get(
    f"{base_url}/v2/stocks/AAPL/quote",
    headers={
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    },
    timeout=30
)

quote = quote_response.json()
current_price = Decimal(quote.get("bp", 275))  # bid price
print(f"  Current price: ${current_price}")

# Try bracket order
print("\nTrying bracket order...")
stop_loss_price = current_price * (Decimal("1") - Decimal("0.08"))
take_profit_price = current_price * (Decimal("1") + Decimal("0.16"))
limit_price = current_price * (Decimal("1") + Decimal("0.01"))

print(f"  Limit: ${limit_price:.2f}")
print(f"  Stop: ${stop_loss_price:.2f}")
print(f"  Take: ${take_profit_price:.2f}")

payload = {
    "symbol": "AAPL",
    "qty": "1",
    "side": "buy",
    "type": "limit",
    "limit_price": str(limit_price),
    "time_in_force": "day",
    "order_class": "bracket",
    "stop_loss": {
        "stop_price": str(stop_loss_price),
    },
    "take_profit": {
        "limit_price": str(take_profit_price),
    },
}

print(f"\nPayload:")
import json
print(json.dumps(payload, indent=2))

response = requests.post(
    f"{base_url}/v2/orders",
    headers={
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    },
    json=payload,
    timeout=30
)

print(f"\nStatus: {response.status_code}")
print(f"Response: {response.text}")
