#!/usr/bin/env python3
"""Capture real Polymarket market data to a JSONL snapshot file.

Usage:
    python scripts/capture.py                   # saves to data/snapshots/snapshot_<timestamp>.jsonl
    python scripts/capture.py --limit 20        # capture 20 markets (default: 50)
    python scripts/capture.py --out /tmp/test.jsonl

No API authentication required. Calls public Gamma and CLOB endpoints.
"""
import argparse
import datetime
import json
import os
import sys

import requests

GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"
DEFAULT_SNAPSHOT_DIR = "data/snapshots"
REQUEST_TIMEOUT = 10  # seconds


def fetch_markets(limit: int = 50) -> list[dict]:
    """Fetch active, CLOB-enabled markets from Gamma API."""
    resp = requests.get(
        f"{GAMMA_URL}/markets",
        params={
            "active": "true",
            "closed": "false",
            "enableOrderBook": "true",
            "limit": limit,
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def parse_market(market: dict) -> dict | None:
    """Parse a Gamma API market object into a snapshot record.

    Returns None and prints a warning if the market cannot be parsed.
    Note: outcomePrices is a stringified JSON array (double-encoded).
    """
    try:
        condition_id = market.get("conditionId", "")
        question = market.get("question", "")

        # outcomePrices is a stringified JSON array: '["0.65", "0.35"]'
        # CRITICAL: must json.loads() before indexing — raw string indexing gives '['
        raw_prices = market.get("outcomePrices", '["0.5", "0.5"]')
        outcome_prices = json.loads(raw_prices)

        # clobTokenIds is also double-encoded: '["token_yes", "token_no"]'
        raw_tokens = market.get("clobTokenIds", "[]")
        clob_token_ids = json.loads(raw_tokens) if raw_tokens else []

        yes_price = float(outcome_prices[0]) if outcome_prices else 0.5
        no_price = float(outcome_prices[1]) if len(outcome_prices) > 1 else 1.0 - yes_price
        volume = float(market.get("volume24hr", 0) or 0)

        return {
            "captured_at": datetime.datetime.utcnow().isoformat(),
            "market_id": condition_id,
            "question": question,
            "yes_price": yes_price,
            "no_price": no_price,
            "volume_24h": volume,
            "yes_token_id": clob_token_ids[0] if clob_token_ids else "",
            "no_token_id": clob_token_ids[1] if len(clob_token_ids) > 1 else "",
        }
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
        print(f"WARNING: skipping market '{market.get('conditionId', '?')}': {exc}", file=sys.stderr)
        return None


def capture_snapshot(output_path: str, limit: int = 50) -> int:
    """Capture markets and write to JSONL file. Returns count of records written."""
    markets = fetch_markets(limit=limit)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    written = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for market in markets:
            record = parse_market(market)
            if record is not None:
                f.write(json.dumps(record) + "\n")
                written += 1

    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture Polymarket snapshot to JSONL")
    parser.add_argument("--limit", type=int, default=50, help="Number of markets to capture")
    parser.add_argument("--out", type=str, default=None, help="Output file path (default: auto-timestamped)")
    args = parser.parse_args()

    if args.out:
        output_path = args.out
    else:
        ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(DEFAULT_SNAPSHOT_DIR, f"snapshot_{ts}.jsonl")

    print(f"Capturing up to {args.limit} markets → {output_path}")
    count = capture_snapshot(output_path, limit=args.limit)
    print(f"Captured {count} markets to {output_path}")


if __name__ == "__main__":
    main()
