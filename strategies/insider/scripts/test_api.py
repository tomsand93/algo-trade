import requests
import json

api_key = "ec6d84e428ccc772c679049d4df5c19f81b49d38b521f37bf8cd6a62e993b41e"

# Test 1: Without Accept-Encoding header (let requests handle gzip)
print("Test 1: Let requests handle compression")
response = requests.post(
    "https://api.sec-api.io/insider-trading",
    headers={
        "Authorization": api_key,
        "Content-Type": "application/json"
    },
    json={"query": "issuer.tradingSymbol:AAPL", "from": 0, "size": 1}
)
print(f"Status: {response.status_code}")
print(f"Content-Encoding: {response.headers.get('Content-Encoding', 'none')}")
print(f"Response length: {len(response.content)}")
if response.status_code == 200:
    data = response.json()
    print(f"Total transactions: {data.get('total', {}).get('value', 0)}")
    if data.get('transactions'):
        txn = data['transactions'][0]
        print(f"Filing date: {txn.get('filedAt')}")
        non_deriv = txn.get('nonDerivativeTable', {})
        txns = non_deriv.get('transactions', [])
        if txns:
            print(f"Transaction code: {txns[0].get('coding', {}).get('code')}")

print("\n" + "="*60)

# Test 2: With explicit no compression
print("\nTest 2: Explicit no compression")
response2 = requests.post(
    "https://api.sec-api.io/insider-trading",
    headers={
        "Authorization": api_key,
        "Content-Type": "application/json",
        "Accept-Encoding": "identity"
    },
    json={"query": "issuer.tradingSymbol:AAPL", "from": 0, "size": 1}
)
print(f"Status: {response2.status_code}")
if response2.status_code == 200:
    data2 = response2.json()
    print(f"Total: {data2.get('total', {}).get('value', 0)}")
