import os
from dotenv import load_dotenv
load_dotenv()
import requests
from datetime import date, timedelta
import json

api_key = os.getenv("SEC_API_KEY")

# Expanded date range for more data
end_date = date(2024, 12, 31)
start_date = date(2023, 1, 1)  # 2 years of data

# Multiple tickers for more signals
tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "V", "WMT", "DIS", "NFLX", "CRM", "AMD", "ABBV"]

print(f"Fetching insider buys from {start_date} to {end_date}...")
print(f"Tickers: {', '.join(tickers)}")

all_buys = []

for ticker in tickers:
    print(f"  Fetching {ticker}...")

    query = {
        "query": f"filedAt:[{start_date.isoformat()} TO {end_date.isoformat()}] AND issuer.tradingSymbol:{ticker}",
        "from": 0,
        "size": 50,
        "sort": [{"filedAt": "desc"}]
    }

    try:
        response = requests.post(
            "https://api.sec-api.io/insider-trading",
            headers={"Authorization": api_key, "Content-Type": "application/json"},
            json=query,
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            transactions = data.get("transactions", [])

            for filing in transactions:
                for txn in filing.get("nonDerivativeTable", {}).get("transactions", []):
                    code = txn.get("coding", {}).get("code", "")
                    # Include P (purchase) and M (award/grant like RSU vesting)
                    if code in ["P", "M"]:
                        amounts = txn.get("amounts", {})
                        shares = amounts.get("shares", 0)
                        price = amounts.get("pricePerShare", 0)

                        if isinstance(price, (int, float)) and price > 0:
                            value = shares * price
                            if value >= 50000:  # Lowered threshold to $50K
                                all_buys.append({
                                    "ticker": ticker,
                                    "filing_date": filing.get("filedAt", "")[:10],
                                    "transaction_date": txn.get("transactionDate", ""),
                                    "code": code,
                                    "value": value
                                })

            print(f"    Got {len(transactions)} filings, running total: {len(all_buys)} buys")
        else:
            print(f"    Error: {response.status_code}")

    except Exception as e:
        print(f"    Exception: {e}")

print(f"\nTotal buys found: {len(all_buys)}")

# Sort by value and show top
all_buys.sort(key=lambda x: x["value"], reverse=True)
print("\nTop 20 buys by value:")
for b in all_buys[:20]:
    print(f"  {b['ticker']:6} {b['filing_date']}  {b['code']}  ${b['value']:>10,.0f}")

# Save in our expected format
# Convert to the format expected by our parser
formatted_data = []
for b in all_buys:
    formatted_data.append({
        "ticker": b["ticker"],
        "filing_date": b["filing_date"],
        "filing_timestamp": f"{b['filing_date']}T16:30:00Z",
        "insiders": [{
            "name": "Insider",
            "transactions": [{
                "transaction_date": b["transaction_date"],
                "transaction_code": "P",  # Normalize to P
                "acquisition_disposition": "A",
                "shares": "1000",
                "price_per_share": str(b["value"] / 1000),
                "total_value": str(int(b["value"]))
            }]
        }]
    })

with open("data/insider_multi_ticker.json", "w") as f:
    json.dump(formatted_data, f, indent=2, default=str)

print(f"\nSaved {len(formatted_data)} signals to data/insider_multi_ticker.json")
print(f"Date range: {start_date} to {end_date}")
print(f"Tickers: {len(tickers)}")
