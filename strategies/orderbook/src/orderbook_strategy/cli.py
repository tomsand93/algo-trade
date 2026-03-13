"""CLI interface for orderbook strategy."""

from pathlib import Path

import click

from .backtest import Backtester
from .config import Config
from .metrics import format_metrics
from .report import write_outputs
from .utils import setup_logging


@click.group()
@click.version_option(version="0.1.0")
def main():
    """Orderbook L2 trading strategy with distribution-based directional probability."""
    pass


@main.command()
@click.option(
    "--trades",
    "-t",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to trades CSV file",
)
@click.option(
    "--book",
    "-b",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to orderbook CSV file",
)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to config YAML file",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=Path("./outputs"),
    help="Output directory for results",
)
def backtest(trades: Path, book: Path, config: Path | None, output: Path):
    """Run backtest on historical data."""
    # Load config
    cfg = Config.from_yaml(config)
    logger = setup_logging(cfg.log_level)

    logger.info(f"Starting backtest with trades={trades}, book={book}")

    # Run backtest
    backtester = Backtester(cfg)
    results = backtester.run(trades, book)

    # Write outputs
    write_outputs(results, output)

    # Print summary
    if "metrics" in results:
        print("\n")
        print(format_metrics(results["metrics"]))


@main.command()
@click.option(
    "--trades",
    "-t",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to trades CSV file",
)
@click.option(
    "--book",
    "-b",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to orderbook CSV file",
)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to config YAML file",
)
def paper(trades: Path, book: Path, config: Path | None):
    """Run paper trading simulation (live mode stub)."""
    cfg = Config.from_yaml(config)
    logger = setup_logging(cfg.log_level)

    logger.info("Starting paper trading simulation")

    # TODO: Implement streaming interface
    logger.warning("Paper trading mode is a stub - streaming interface not yet implemented")
    logger.info("For now, use backtest mode to validate strategy logic")


if __name__ == "__main__":
    main()
