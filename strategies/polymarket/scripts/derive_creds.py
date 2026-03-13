#!/usr/bin/env python3
"""One-time credential derivation helper for Polymarket CLOB API.

Run this ONCE to derive your API credentials from your wallet private key.
Copy the output to your .env file before running --mode live.

Prerequisites:
1. Set POLYMARKET_PRIVATE_KEY in .env (your wallet private key, prefixed with 0x)
2. Run: python scripts/derive_creds.py
3. Copy the printed POLYMARKET_API_KEY / SECRET / PASSPHRASE into .env

Note: signature_type affects which wallet type is used:
  0 = EOA (standard MetaMask/hardware wallet) — default
  1 = POLY_PROXY (Magic Link / email wallet from polymarket.com)
  2 = GNOSIS_SAFE (multisig proxy — used by some Polymarket.com accounts)

Set SIGNATURE_TYPE in .env if not using an EOA wallet.
"""
import os
import sys


def main() -> None:
    # Load .env manually (py-clob-client requires the private key, not Settings)
    try:
        from dotenv import load_dotenv
        load_dotenv(".env")
    except ImportError:
        pass  # python-dotenv optional; user can set env vars directly

    pk = os.getenv("POLYMARKET_PRIVATE_KEY", "").strip()
    if not pk:
        print("ERROR: POLYMARKET_PRIVATE_KEY not set in .env")
        print("Add your wallet private key to .env:")
        print("  POLYMARKET_PRIVATE_KEY=0x<your_private_key>")
        sys.exit(1)

    signature_type = int(os.getenv("SIGNATURE_TYPE", "0"))

    try:
        from py_clob_client.client import ClobClient
    except ImportError:
        print("ERROR: py-clob-client not installed.")
        print("Run: pip install py-clob-client web3==6.14.0")
        sys.exit(1)

    print("Connecting to Polymarket CLOB (Polygon mainnet)...")
    try:
        client = ClobClient(
            "https://clob.polymarket.com",
            key=pk,
            chain_id=137,
            signature_type=signature_type,
        )
        creds = client.create_or_derive_api_creds()
    except Exception as exc:
        print(f"ERROR: Failed to derive credentials: {exc}")
        print("Check that your private key is valid and you have network access.")
        sys.exit(1)

    print("\nAdd these to your .env file:\n")
    print(f"POLYMARKET_API_KEY={creds.api_key}")
    print(f"POLYMARKET_API_SECRET={creds.api_secret}")
    print(f"POLYMARKET_API_PASSPHRASE={creds.api_passphrase}")
    print("\nDone. You can now run: python run.py --mode paper")


if __name__ == "__main__":
    main()
