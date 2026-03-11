"""
Test signal generation from cached SEC data.
Uses the insider_multi_ticker.json we already downloaded.
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from datetime import date
from decimal import Decimal

from src.data.sec_api_client import load_cached_data
from src.normalize.form4_parser import normalize_transactions
from src.signals.single_buy_threshold import SingleBuyThresholdSignal
from src.data.price_provider import get_price_provider

print("=" * 60)
print("Signal Generation Test (Cached Data)")
print("=" * 60)

# Load cached data
cache_path = "data/insider_multi_ticker.json"
print(f"\nLoading cached data from {cache_path}")

raw_data = load_cached_data(cache_path)
print(f"Loaded {len(raw_data)} raw filings")

# Normalize
print("\nNormalizing to InsiderTransaction objects...")
transactions = normalize_transactions(raw_data, source="secapi")
print(f"Normalized {len(transactions)} transactions")

# Show sample
if transactions:
    t = transactions[0]
    print(f"\nSample transaction:")
    print(f"  Ticker: {t.ticker}")
    print(f"  Insider: {t.insider_name}")
    print(f"  Date: {t.transaction_date}")
    print(f"  Value: ${t.value_usd:,.0f}")

# Generate signals with different thresholds
for threshold in [100000, 75000, 50000]:
    print(f"\n" + "-" * 60)
    print(f"Testing with ${threshold:,.0f} threshold")
    print("-" * 60)

    price_provider = get_price_provider("yfinance")
    signal_gen = SingleBuyThresholdSignal(
        threshold_usd=Decimal(str(threshold)),
        min_dvol=None,
        price_provider=price_provider,
        require_prices=False,
    )

    signals = signal_gen.generate_signals(
        transactions=transactions,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )

    print(f"Generated {len(signals)} signals")

    if signals:
        print(f"\nTop 5 by value:")
        for sig in sorted(signals, key=lambda s: s.buy_value_usd, reverse=True)[:5]:
            print(f"  {sig.ticker:<6} {sig.signal_date} ${sig.buy_value_usd:>10,.0f}")

print("\n" + "=" * 60)
print("Test complete!")
print("=" * 60)
