"""
Test bracket order directly with Alpaca API.
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

# Use yfinance for price
import yfinance as yf
ticker = yf.Ticker("AAPL")
current_price = Decimal(ticker.history(period="1d")["Close"].iloc[-1])
print(f"AAPL current price: ${current_price}")

# Calculate prices
stop_loss_price = current_price * (Decimal("1") - Decimal("0.08"))
take_profit_price = current_price * (Decimal("1") + Decimal("0.16"))

# Try different payloads
test_cases = [
    {
        "name": "Market bracket (may fail when closed)",
        "payload": {
            "symbol": "AAPL",
            "qty": "1",
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
            "order_class": "bracket",
            "stop_loss": {"stop_price": str(stop_loss_price)},
            "take_profit": {"limit_price": str(take_profit_price)},
        }
    },
    {
        "name": "Limit bracket (with limit at current price)",
        "payload": {
            "symbol": "AAPL",
            "qty": "1",
            "side": "buy",
            "type": "limit",
            "limit_price": str(current_price),
            "time_in_force": "day",
            "order_class": "bracket",
            "stop_loss": {"stop_price": str(stop_loss_price)},
            "take_profit": {"limit_price": str(take_profit_price)},
        }
    },
    {
        "name": "Limit bracket (with limit 2% above current)",
        "payload": {
            "symbol": "AAPL",
            "qty": "1",
            "side": "buy",
            "type": "limit",
            "limit_price": str(current_price * Decimal("1.02")),
            "time_in_force": "day",
            "order_class": "bracket",
            "stop_loss": {"stop_price": str(stop_loss_price)},
            "take_profit": {"limit_price": str(take_profit_price)},
        }
    },
]

for test in test_cases:
    print(f"\n{'='*60}")
    print(f"Test: {test['name']}")
    print(f"{'='*60}")

    response = requests.post(
        f"{base_url}/v2/orders",
        headers={
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
        },
        json=test["payload"],
        timeout=30
    )

    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"SUCCESS! Order ID: {data.get('id')}")
    else:
        print(f"FAILED: {response.text[:200]}")
