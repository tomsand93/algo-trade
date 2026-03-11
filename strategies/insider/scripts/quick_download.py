import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from datetime import date
import requests
import json

# Get API key
api_key = os.getenv("SEC_API_KEY")
if not api_key:
    print("Error: SEC_API_KEY not found in environment")
    sys.exit(1)

# Test fetching AAPL insider data for 2024
start_date = date(2024, 1, 1)
end_date = date(2024, 12, 31)

print(f"Fetching AAPL insider buys from {start_date} to {end_date}...")

# Manually build query for AAPL
query = {
    "query": f"filedAt:[{start_date.isoformat()} TO {end_date.isoformat()}] AND issuer.tradingSymbol:AAPL",
    "from": 0,
    "size": 1000,
    "sort": [{"filedAt": "desc"}]
}

try:
    response = requests.post(
        "https://api.sec-api.io/insider-trading",
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json"
        },
        json=query,
        timeout=30
    )
    print(f"Status: {response.status_code}")
    response.raise_for_status()
    data = response.json()

    transactions = data.get("transactions", [])
    print(f"Got {len(transactions)} AAPL filings")

    # Extract P-code (purchase) transactions
    buys = []
    for filing in transactions:
        ticker = filing.get("issuer", {}).get("tradingSymbol", "")
        filing_date = filing.get("filedAt", "")[:10]

        for txn in filing.get("nonDerivativeTable", {}).get("transactions", []):
            code = txn.get("coding", {}).get("code", "")
            if code == "P":  # Open market purchase
                amounts = txn.get("amounts", {})
                shares = amounts.get("shares", 0)
                price = amounts.get("pricePerShare", 0)
                if isinstance(price, (int, float)):
                    value = shares * price
                    if value >= 100000:  # $100K threshold
                        buys.append({
                            "ticker": ticker,
                            "filing_date": filing_date,
                            "value": value
                        })

    print(f"Found {len(buys)} buys over $100K")
    for b in buys[:10]:
        print(f"  {b['ticker']}: {b['filing_date']} - ${b['value']:,.0f}")

    # Save
    with open("data/insider_aapl_sample.json", "w") as f:
        json.dump(buys, f, indent=2, default=str)
    print(f"\nSaved to data/insider_aapl_sample.json")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
