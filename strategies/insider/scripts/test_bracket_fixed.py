"""
Test bracket order with proper rounding.
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from decimal import Decimal
import requests
import yfinance as yf

api_key = os.getenv("ALPACA_API_KEY")
api_secret = os.getenv("ALPACA_API_SECRET")
base_url = "https://paper-api.alpaca.markets"

# Get current price
ticker = yf.Ticker("AAPL")
current_price = Decimal(ticker.history(period="1d")["Close"].iloc[-1])
print(f"AAPL current price: ${current_price}")

# Calculate and round prices
quantize = Decimal("0.01")
stop_loss_pct = Decimal("0.08")
take_profit_pct = Decimal("0.16")

stop_loss_price = (current_price * (Decimal("1") - stop_loss_pct)).quantize(quantize)
take_profit_price = (current_price * (Decimal("1") + take_profit_pct)).quantize(quantize)
limit_price = (current_price * (Decimal("1") + Decimal("0.01"))).quantize(quantize)

print(f"  Limit: ${limit_price}")
print(f"  Stop: ${stop_loss_price}")
print(f"  Take: ${take_profit_price}")

payload = {
    "symbol": "AAPL",
    "qty": "1",
    "side": "buy",
    "type": "limit",
    "limit_price": str(limit_price),
    "time_in_force": "day",
    "order_class": "bracket",
    "stop_loss": {"stop_price": str(stop_loss_price)},
    "take_profit": {"limit_price": str(take_profit_price)},
}

print(f"\nSubmitting order...")

response = requests.post(
    f"{base_url}/v2/orders",
    headers={
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    },
    json=payload,
    timeout=30
)

print(f"Status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"SUCCESS! Order ID: {data.get('id')}")
else:
    print(f"FAILED: {response.text}")
