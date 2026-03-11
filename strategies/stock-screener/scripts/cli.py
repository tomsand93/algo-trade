#!/usr/bin/env python3
"""Stock screener CLI entry point."""

import argparse
import asyncio
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.performance import PerformanceTracker
from src.providers import FinnhubNewsProvider, OpenBBProvider, YFinanceProvider
from src.scoring import StockRanker
from src.screener import StockFilter
from src.screener.models import ScreenerConfig
from src.utils import OutputFormatter, log_runtime, setup_logging


@log_runtime
async def run_screener(config_path: str = "configs/example.yaml", track_performance: bool = True):
    """Run the screener with the configured providers, filters, and outputs."""
    load_dotenv()

    with open(config_path, "r", encoding="utf-8") as handle:
        config_dict = yaml.safe_load(handle)

    config = ScreenerConfig(**config_dict)
    logger = setup_logging(config.output.get("save_dir", "results"))

    symbols = config.universe.get("list", [])
    logger.info("Starting screener with %d symbols", len(symbols))

    price_provider = YFinanceProvider()

    try:
        fund_provider = OpenBBProvider()
    except ImportError as exc:
        logger.warning("OpenBB not available: %s", exc)
        fund_provider = None

    news_provider = None
    if config.news.get("enabled"):
        try:
            news_provider = FinnhubNewsProvider()
        except (ImportError, ValueError) as exc:
            logger.warning("News provider not available: %s", exc)

    ranker = StockRanker(config.ranking)
    stock_filter = StockFilter(config, ranker)

    logger.info("Fetching price data...")
    price_data = await price_provider.get_prices_batch(symbols)

    if fund_provider:
        logger.info("Fetching fundamental data...")
        fund_data = await fund_provider.get_fundamentals_batch(symbols)
    else:
        fund_data = {}

    news_data = {}
    if news_provider:
        logger.info("Fetching news headlines...")
        for symbol in symbols:
            headlines = await news_provider.get_news(
                symbol,
                days_back=config.news.get("days_back", 7),
                limit=config.news.get("max_headlines", 5),
            )
            if headlines:
                news_data[symbol] = headlines

    logger.info("Applying screening criteria...")
    results = stock_filter.filter_stocks(price_data, fund_data, news_data or None)
    logger.info("Found %d passing stocks", len(results))

    formatter = OutputFormatter(config.output.get("save_dir", "results"))
    formats = config.output.get("format", ["markdown"])

    if "markdown" in formats:
        formatter.save_markdown(results, price_data, fund_data, news_data or None)
    if "csv" in formats:
        formatter.save_csv(results, price_data, fund_data)
    if "json" in formats:
        formatter.save_json(results, price_data, fund_data, news_data or None)

    if track_performance and results:
        try:
            tracker = PerformanceTracker()
            tracker.save_screening(results, price_data, config_dict)
        except Exception as exc:
            logger.warning("Could not save performance snapshot: %s", exc)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock Screener")
    parser.add_argument("--config", default="configs/example.yaml", help="Path to YAML config")
    parser.add_argument(
        "--no-performance-track",
        action="store_true",
        help="Skip saving screening snapshots for later analysis",
    )
    args = parser.parse_args()

    asyncio.run(run_screener(args.config, track_performance=not args.no_performance_track))


if __name__ == "__main__":
    main()
