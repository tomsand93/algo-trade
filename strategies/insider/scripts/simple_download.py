import os
from dotenv import load_dotenv
load_dotenv()
import requests
from datetime import date

api_key = os.getenv("SEC_API_KEY")
start_date = date(2024, 1, 1)
end_date = date(2024, 12, 31)

print(f"Fetching AAPL insider buys from {start_date} to {end_date}...")
print(f"Using key: {api_key[:20]}...")

query = {
    "query": f"filedAt:[{start_date.isoformat()} TO {end_date.isoformat()}] AND issuer.tradingSymbol:AAPL",
    "from": 0,
    "size": 50,
    "sort": [{"filedAt": "desc"}]
}

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

if response.status_code == 200:
    data = response.json()
    transactions = data.get("transactions", [])
    print(f"Got {len(transactions)} AAPL filings")

    # Extract P-code transactions
    buys = []
    for filing in transactions:
        for txn in filing.get("nonDerivativeTable", {}).get("transactions", []):
            code = txn.get("coding", {}).get("code", "")
            if code == "P":
                amounts = txn.get("amounts", {})
                shares = amounts.get("shares", 0)
                price = amounts.get("pricePerShare", 0)
                if isinstance(price, (int, float)) and price > 0:
                    value = shares * price
                    if value >= 100000:
                        buys.append({
                            "ticker": "AAPL",
                            "filing_date": filing.get("filedAt", "")[:10],
                            "value": value
                        })

    print(f"Found {len(buys)} buys over $100K")
    for b in buys[:5]:
        print(f"  AAPL: {b['filing_date']} - ${b['value']:,.0f}")

    import json
    with open("data/insider_aapl.json", "w") as f:
        json.dump(buys, f, indent=2, default=str)
    print(f"Saved to data/insider_aapl.json")
else:
    print(f"Error: {response.text[:200]}")
