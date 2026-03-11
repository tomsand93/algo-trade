"""
Debug SEC API query to see what's being sent.
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
print(f"API Key: {api_key[:20]}...")

# Test the query that worked before
test_query = {
    "query": "filedAt:[2024-01-01 TO 2024-12-31] AND issuer.tradingSymbol:AAPL",
    "from": 0,
    "size": 10,
    "sort": [{"filedAt": "desc"}]
}

print(f"\nQuery being sent:")
print(json.dumps(test_query, indent=2))

response = requests.post(
    "https://api.sec-api.io/insider-trading",
    headers={"Authorization": api_key, "Content-Type": "application/json"},
    json=test_query,
    timeout=30
)

print(f"\nStatus: {response.status_code}")
print(f"Response: {response.text[:500]}")
