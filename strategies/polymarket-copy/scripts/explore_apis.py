"""
Script to explore Polymarket API endpoints.

This script tests the Data API and Gamma API to understand:
- Response shapes and data structures
- Rate limits
- Authentication requirements
"""

import json
from datetime import datetime, timedelta

from pmirror.data import BaseHttpClient


def explore_data_api():
    """Explore the Polymarket Data API."""
    print("=" * 60)
    print("Exploring Data API: https://data-api.polymarket.com")
    print("=" * 60)

    client = BaseHttpClient("https://data-api.polymarket.com", client_name="DataAPI")

    # Test 1: Get recent trades
    print("\n1. Testing /trades endpoint...")
    try:
        response = client.get("/trades", params={"limit": 5})
        trades = response.json()
        print(f"   Status: {response.status_code}")
        print(f"   Sample trade:")
        if trades:
            trade = trades[0]
            for key, value in list(trade.items())[:10]:
                print(f"     {key}: {value}")
    except Exception as e:
        print(f"   Error: {e}")

    # Test 2: Get trades by wallet
    print("\n2. Testing /trades by wallet endpoint...")
    try:
        # Use a known active wallet
        wallet = "0x0000000000000000000000000000000000000000"
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        response = client.get(
            "/trades",
            params={
                "maker": wallet,
                "start": int(start_date.timestamp()),
                "end": int(end_date.timestamp()),
                "limit": 5,
            },
        )
        trades = response.json()
        print(f"   Status: {response.status_code}")
        print(f"   Results: {len(trades) if isinstance(trades, list) else 'N/A'}")
    except Exception as e:
        print(f"   Error: {e}")

    # Test 3: Get markets
    print("\n3. Testing /markets endpoint...")
    try:
        response = client.get("/markets", params={"limit": 3})
        markets = response.json()
        print(f"   Status: {response.status_code}")
        if markets:
            market = markets[0]
            print(f"   Sample market keys: {list(market.keys())[:15]}")
    except Exception as e:
        print(f"   Error: {e}")

    # Test 4: Get specific market
    print("\n4. Testing /markets/{id} endpoint...")
    try:
        # First get a market ID
        response = client.get("/markets", params={"limit": 1})
        markets = response.json()
        if markets and "condition_id" in markets[0]:
            market_id = markets[0]["condition_id"]
            response = client.get(f"/markets/{market_id}")
            market = response.json()
            print(f"   Status: {response.status_code}")
            print(f"   Market: {market.get('question', 'N/A')}")
            print(f"   Outcomes: {market.get('outcomes', 'N/A')}")
            print(f"   Resolution: {market.get('resolution', 'N/A')}")
    except Exception as e:
        print(f"   Error: {e}")

    client.close()


def explore_gamma_api():
    """Explore the Polymarket Gamma API."""
    print("\n" + "=" * 60)
    print("Exploring Gamma API: https://gamma-api.polymarket.com")
    print("=" * 60)

    client = BaseHttpClient("https://gamma-api.polymarket.com", client_name="GammaAPI")

    # Test 1: Get markets
    print("\n1. Testing /markets endpoint...")
    try:
        response = client.get("/markets")
        markets = response.json()
        print(f"   Status: {response.status_code}")
        print(f"   Total markets: {len(markets) if isinstance(markets, list) else 'N/A'}")

        if isinstance(markets, list) and markets:
            market = markets[0]
            print(f"   Sample market keys: {list(market.keys())[:15]}")
    except Exception as e:
        print(f"   Error: {e}")

    # Test 2: Get market with query params
    print("\n2. Testing /markets with query params...")
    try:
        response = client.get("/markets", params={"limit": 2})
        markets = response.json()
        print(f"   Status: {response.status_code}")
        if isinstance(markets, list):
            print(f"   Returned: {len(markets)} markets")
    except Exception as e:
        print(f"   Error: {e}")

    # Test 3: Get specific market by slug
    print("\n3. Testing /markets/{slug} endpoint...")
    try:
        # First get a market slug
        response = client.get("/markets", params={"limit": 1})
        markets = response.json()
        if isinstance(markets, list) and markets and "slug" in markets[0]:
            slug = markets[0]["slug"]
            response = client.get(f"/markets/{slug}")
            market = response.json()
            print(f"   Status: {response.status_code}")
            print(f"   Market slug: {slug}")
            print(f"   Question: {market.get('question', 'N/A')}")
    except Exception as e:
        print(f"   Error: {e}")

    client.close()


def test_rate_limiting():
    """Test rate limiting behavior."""
    print("\n" + "=" * 60)
    print("Testing Rate Limits")
    print("=" * 60)

    client = BaseHttpClient("https://data-api.polymarket.com", client_name="RateLimitTest")

    print("\n1. Sending multiple rapid requests...")
    success_count = 0
    rate_limited = False

    for i in range(20):
        try:
            response = client.get("/markets", params={"limit": 1})
            if response.status_code == 429:
                rate_limited = True
                print(f"   Request {i+1}: Rate limited (429)")
                break
            elif response.status_code == 200:
                success_count += 1
        except Exception as e:
            print(f"   Request {i+1}: Error - {e}")
            break

    print(f"   Successful requests: {success_count}")
    print(f"   Rate limited: {'Yes' if rate_limited else 'No (not hit in 20 requests)'}")

    client.close()


if __name__ == "__main__":
    print("Polymarket API Explorer")
    print("=" * 60)
    print(f"Time: {datetime.now().isoformat()}")
    print()

    explore_data_api()
    explore_gamma_api()
    test_rate_limiting()

    print("\n" + "=" * 60)
    print("Exploration complete!")
    print("=" * 60)
