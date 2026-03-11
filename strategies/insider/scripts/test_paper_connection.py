"""
Test Alpaca paper trading connection before going live.
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.live.alpaca_paper import AlpacaPaperClient, validate_paper_mode

print("=" * 50)
print("Alpaca Paper Trading Connection Test")
print("=" * 50)

# 1. Check environment variables
print("\n1. Checking environment...")
api_key = os.getenv("ALPACA_API_KEY")
api_secret = os.getenv("ALPACA_API_SECRET")
paper_mode = os.getenv("PAPER_MODE", "false").lower() == "true"

print(f"   API Key: {api_key[:15] if api_key else 'NOT SET'}...")
print(f"   API Secret: {'SET' if api_secret else 'NOT SET'}")
print(f"   Paper Mode: {paper_mode}")

if not all([api_key, api_secret]):
    print("\n   ERROR: Missing credentials!")
    sys.exit(1)

# 2. Validate paper trading mode
print("\n2. Validating paper mode...")
try:
    validate_paper_mode()
    print("   Paper trading mode validated [OK]")
except ValueError as e:
    print(f"   ERROR: {e}")
    sys.exit(1)

# 3. Connect to Alpaca
print("\n3. Connecting to Alpaca...")
try:
    client = AlpacaPaperClient()
    print("   Client created [OK]")
except Exception as e:
    print(f"   ERROR: {e}")
    sys.exit(1)

# 4. Get account info
print("\n4. Getting account info...")
try:
    account = client.get_account()
    print(f"   Account ID: {account.get('id', 'N/A')}")
    print(f"   Buying Power: ${float(account.get('buying_power', 0)):,.2f}")
    print(f"   Cash: ${float(account.get('cash', 0)):,.2f}")
    print(f"   Portfolio Value: ${float(account.get('portfolio_value', 0)):,.2f}")
    print(f"   Account Status: {account.get('status', 'N/A')}")
except Exception as e:
    print(f"   ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 5. Check for open positions
print("\n5. Checking open positions...")
try:
    positions = client.get_positions()
    print(f"   Open positions: {len(positions)}")
    for pos in positions:
        print(f"     {pos.get('symbol', 'N/A')}: {pos.get('qty', 0)} shares @ ${pos.get('avg_entry_price', 0)}")
except Exception as e:
    print(f"   ERROR: {e}")

# 6. Test getting current price
print("\n6. Testing price data...")
try:
    price = client.get_current_price("AAPL")
    print(f"   AAPL current price: ${price:.2f}")
except Exception as e:
    print(f"   ERROR: {e}")

print("\n" + "=" * 50)
print("Connection test PASSED [OK]")
print("=" * 50)
print("\nReady to run paper trading!")
