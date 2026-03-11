"""
Debug raw SEC API response to see the data structure.
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from datetime import date
import requests
import json

api_key = os.getenv("SEC_API_KEY")

query = {
    "query": "filedAt:[2024-11-01 TO 2024-12-31] AND issuer.tradingSymbol:AAPL",
    "from": 0,
    "size": 10,
    "sort": [{"filedAt": "desc"}]
}

response = requests.post(
    "https://api.sec-api.io/insider-trading",
    headers={"Authorization": api_key, "Content-Type": "application/json"},
    json=query,
    timeout=30
)

data = response.json()
transactions = data.get("transactions", [])

print(f"Got {len(transactions)} filings\n")

# Show first filing structure
if transactions:
    filing = transactions[0]
    print("Filing structure:")
    print(f"  ticker: {filing.get('issuer', {}).get('tradingSymbol')}")
    print(f"  filedAt: {filing.get('filedAt')}")
    print(f"  periodOfReport: {filing.get('periodOfReport')}")

    # Show transactions
    non_deriv = filing.get("nonDerivativeTable", {})
    txns = non_deriv.get("transactions", [])
    print(f"\n  Non-derivative transactions: {len(txns)}")

    for i, txn in enumerate(txns[:3]):
        coding = txn.get("coding", {})
        amounts = txn.get("amounts", {})
        print(f"\n  Transaction {i+1}:")
        print(f"    code: {coding.get('code')}")
        print(f"    acquiredDisposed: {amounts.get('acquiredDisposedCode')}")
        print(f"    shares: {amounts.get('shares')}")
        print(f"    pricePerShare: {amounts.get('pricePerShare')}")
        print(f"    transactionDate: {txn.get('transactionDate')}")
