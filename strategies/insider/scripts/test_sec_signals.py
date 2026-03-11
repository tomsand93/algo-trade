"""
Test SEC API signal fetching (can run any time).
Tests the complete signal pipeline: SEC API -> normalize -> generate signals.
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from datetime import date, timedelta
from decimal import Decimal

from src.data.sec_api_client import SECAPIClient
from src.normalize.form4_parser import normalize_transactions
from src.signals.single_buy_threshold import SingleBuyThresholdSignal
from src.data.price_provider import get_price_provider

print("=" * 60)
print("SEC API Signal Fetch Test")
print("=" * 60)

# Test parameters - Use 2024 dates since SEC API only has historical data
end_date = date(2024, 12, 31)
start_date = date(2024, 11, 1)  # Nov-Dec 2024
threshold = Decimal("50000")  # Lower threshold for testing

print(f"\nFetching SEC data from {start_date} to {end_date}")
print(f"Threshold: ${threshold:,.0f}")
print()

# Step 1: Fetch from SEC API
print("-" * 60)
print("Step 1: Fetching from SEC-API.io...")
print("-" * 60)

sec_client = SECAPIClient()

# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

raw_data = sec_client.fetch_insider_trades(
    start_date=start_date,
    end_date=end_date
)

print(f"Fetched {len(raw_data)} raw filings")

if not raw_data:
    print("\nNo data returned. This could mean:")
    print("  - No insider buys in the date range")
    print("  - SEC API rate limiting")
    print("  - API key issue")
    sys.exit(1)

# Show sample of raw data
print(f"\nSample raw filing:")
for key in list(raw_data[0].keys())[:5]:
    print(f"  {key}: {raw_data[0][key]}")

# Step 2: Normalize transactions
print(f"\n" + "-" * 60)
print("Step 2: Normalizing to InsiderTransaction objects...")
print("-" * 60)

transactions = normalize_transactions(raw_data, source="secapi")
print(f"Normalized {len(transactions)} transactions")

# Show sample transaction
if transactions:
    t = transactions[0]
    print(f"\nSample transaction:")
    print(f"  Ticker: {t.ticker}")
    print(f"  Insider: {t.insider_name}")
    print(f"  Date: {t.transaction_date}")
    print(f"  Value: ${t.value_usd:,.0f}")
    print(f"  Code: {t.transaction_code}")

# Step 3: Generate signals
print(f"\n" + "-" * 60)
print("Step 3: Generating trading signals...")
print("-" * 60)

price_provider = get_price_provider("yfinance")
signal_gen = SingleBuyThresholdSignal(
    threshold_usd=threshold,
    min_dvol=None,  # No liquidity filter for testing
    price_provider=price_provider,
    require_prices=False,
)

signals = signal_gen.generate_signals(
    transactions=transactions,
    start_date=start_date,
    end_date=end_date,
)

print(f"\nGenerated {len(signals)} signals")

if signals:
    print(f"\nSignals (top 10):")
    print(f"{'Ticker':<8} {'Signal Date':<12} {'Filing Date':<12} {'Value':>12} {'Insider':<20}")
    print("-" * 70)
    for sig in sorted(signals, key=lambda s: s.buy_value_usd, reverse=True)[:10]:
        print(f"{sig.ticker:<8} {sig.signal_date.strftime('%Y-%m-%d'):<12} {sig.filing_date.strftime('%Y-%m-%d'):<12} ${sig.buy_value_usd:>10,.0f} {sig.insider_name[:20]:<20}")

print("\n" + "=" * 60)
print("Test complete!")
print("=" * 60)
