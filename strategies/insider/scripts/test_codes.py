import requests
import json

api_key = "ec6d84e428ccc772c679049d4df5c19f81b49d38b521f37bf8cd6a62e993b41e"

# Test for P-code (open market purchase) transactions
print("Testing for P-code (open market purchase) transactions...")
response = requests.post(
    "https://api.sec-api.io/insider-trading",
    headers={
        "Authorization": api_key,
        "Content-Type": "application/json"
    },
    json={"query": "transactionCode:P", "from": 0, "size": 10}
)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"Total P-code transactions: {data.get('total', {}).get('value', 0)}")
    if data.get('transactions'):
        for t in data['transactions'][:3]:
            print(f"  {t.get('issuer', {}).get('tradingSymbol', 'N/A')}: {t.get('filedAt')[:10]}")

print("\n" + "="*60)
print("Testing for M-code (grant/award) transactions...")
response2 = requests.post(
    "https://api.sec-api.io/insider-trading",
    headers={
        "Authorization": api_key,
        "Content-Type": "application/json"
    },
    json={"query": "transactionCode:M", "from": 0, "size": 3}
)
if response2.status_code == 200:
    data2 = response2.json()
    print(f"Total M-code transactions: {data2.get('total', {}).get('value', 0)}")

print("\n" + "="*60)
print("Testing without transaction code filter (recent filings)...")
response3 = requests.post(
    "https://api.sec-api.io/insider-trading",
    headers={
        "Authorization": api_key,
        "Content-Type": "application/json"
    },
    json={"query": "AAPL", "from": 0, "size": 5}
)
if response3.status_code == 200:
    data3 = response3.json()
    print(f"Total AAPL: {data3.get('total', {}).get('value', 0)}")
    # Check transaction codes
    codes = {}
    for t in data3.get('transactions', []):
        for txn in t.get('nonDerivativeTable', {}).get('transactions', []):
            code = txn.get('coding', {}).get('code', '?')
            codes[code] = codes.get(code, 0) + 1
    print(f"Transaction codes found: {codes}")
