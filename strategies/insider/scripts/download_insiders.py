#!/usr/bin/env python3
"""
Download insider trading data from SEC-API.io.

Usage:
    python scripts/download_insiders.py --start 2024-01-01 --end 2024-12-31

Or use lookback:
    python scripts/download_insiders.py --lookback 365
"""
import argparse
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.data.sec_api_client import download_insider_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download insider trading data from SEC-API.io"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--start",
        type=str,
        help="Start date (YYYY-MM-DD)"
    )
    group.add_argument(
        "--lookback",
        type=int,
        help="Lookback period in days from today"
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="End date (YYYY-MM-DD, default: today)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/insider_transactions.json",
        help="Output file path"
    )
    parser.add_argument(
        "--source",
        type=str,
        default="secapi",
        choices=["secapi", "edgar"],
        help="Data source (default: secapi)"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Parse dates
    if args.lookback:
        end_date = date.today()
        start_date = end_date - timedelta(days=args.lookback)
        logger.info(f"Lookback: {args.lookback} days from {end_date}")
    else:
        start_date = date.fromisoformat(args.start)
        end_date = date.fromisoformat(args.end) if args.end else date.today()

    logger.info(f"Downloading insider data from {start_date} to {end_date}")

    # Check for API key
    if args.source == "secapi":
        api_key = os.getenv("SEC_API_KEY")
        if not api_key:
            logger.error(
                "SEC_API_KEY environment variable not found. "
                "Get your key at https://sec-api.io/"
            )
            return 1

    # Download data
    try:
        download_insider_data(
            start_date=start_date,
            end_date=end_date,
            output_path=args.output,
            source=args.source,
        )
        logger.info(f"Download complete: {args.output}")
        return 0
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
