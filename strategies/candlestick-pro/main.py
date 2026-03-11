"""
Candlestick Pro - Main Entry Point

A disciplined, explainable candlestick pattern trading system
with dynamic timeframe selection and adaptive risk management.

Usage:
    python main.py --mode analyze --symbol BTC/USDT
    python main.py --mode backtest --data data/btc_1h.csv --pattern engulfing
    python main.py --mode scan --symbols BTC/USDT,ETH/USDT
"""
import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Configure logging
import os
log_dir = Path(__file__).parent / 'logs'
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_dir / 'trading.log')
    ]
)

logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.models import PatternType, TimeFrameStyle, BacktestConfig
from src.strategy import CandlestickStrategy
from src.data_fetcher import DataFetcher


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Candlestick Pro - Pattern Trading System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze live market and generate trading idea
  python main.py --mode analyze --symbol BTC/USDT

  # Run backtest on historical data
  python main.py --mode backtest --data data/btc_1h.csv --pattern engulfing

  # Scan multiple symbols
  python main.py --mode scan --symbols BTC/USDT,ETH/USDT,SOL/USDT

  # Save market data for later analysis
  python main.py --mode fetch --symbol BTC/USDT --output data/btc.csv
        """
    )

    parser.add_argument(
        '--mode',
        type=str,
        choices=['analyze', 'backtest', 'scan', 'fetch'],
        default='analyze',
        help='Execution mode'
    )

    parser.add_argument(
        '--symbol',
        type=str,
        default='BTC/USDT',
        help='Trading symbol (e.g., BTC/USDT)'
    )

    parser.add_argument(
        '--symbols',
        type=str,
        help='Comma-separated symbols for scan mode'
    )

    parser.add_argument(
        '--pattern',
        type=str,
        choices=['engulfing', 'pin_bar', 'morning_star', 'evening_star', 'inside_bar'],
        default='engulfing',
        help='Pattern to detect'
    )

    parser.add_argument(
        '--style',
        type=str,
        choices=['scalping', 'intraday', 'swing'],
        default='intraday',
        help='Trading style (affects timeframe preference)'
    )

    parser.add_argument(
        '--data',
        type=str,
        help='Path to CSV data file for backtest'
    )

    parser.add_argument(
        '--output',
        type=str,
        help='Output path for saving results'
    )

    parser.add_argument(
        '--min-rr',
        type=float,
        default=2.0,
        help='Minimum risk-reward ratio (default: 2.0)'
    )

    parser.add_argument(
        '--min-confidence',
        type=float,
        default=0.5,
        help='Minimum confidence score (default: 0.5)'
    )

    parser.add_argument(
        '--timeframe',
        type=str,
        help='Specific timeframe for backtest (auto-selected for analyze)'
    )

    return parser.parse_args()


def mode_analyze(args):
    """Analyze live market and generate trading idea."""
    logger.info(f"Analyzing {args.symbol} for {args.pattern} pattern...")

    # Map pattern string to enum
    pattern_map = {
        'engulfing': PatternType.ENGULFING,
        'pin_bar': PatternType.PIN_BAR,
        'morning_star': PatternType.MORNING_STAR,
        'evening_star': PatternType.EVENING_STAR,
        'inside_bar': PatternType.INSIDE_BAR,
    }

    # Map style string to enum
    style_map = {
        'scalping': TimeFrameStyle.SCALPING,
        'intraday': TimeFrameStyle.INTRADAY,
        'swing': TimeFrameStyle.SWING,
    }

    # Initialize strategy
    strategy = CandlestickStrategy(
        pattern_type=pattern_map[args.pattern],
        style=style_map[args.style],
        min_rr_ratio=args.min_rr,
        min_confidence=args.min_confidence
    )

    # Fetch live data
    fetcher = DataFetcher(exchange_id="binance", testnet=True)

    # Define timeframes based on style
    style_timeframes = {
        'scalping': ['1m', '5m', '15m'],
        'intraday': ['5m', '15m', '1h', '4h'],
        'swing': ['1h', '4h', '1d'],
    }

    timeframes = style_timeframes[args.style]

    logger.info(f"Fetching data for timeframes: {timeframes}")
    timeframe_data = fetcher.fetch_multiple_timeframes(
        symbol=args.symbol,
        timeframes=timeframes,
        limit=500
    )

    if not timeframe_data:
        logger.error("No data fetched. Check symbol and exchange connection.")
        return

    # Analyze
    idea = strategy.analyze(timeframe_data, args.symbol)

    if idea:
        print("\n" + str(idea))

        # Save to file
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w') as f:
                json.dump(idea.to_dict(), f, indent=2)

            logger.info(f"\nTrading idea saved to {args.output}")
    else:
        print("\n" + "=" * 70)
        print("NO TRADING SETUP FOUND")
        print("=" * 70)
        print(f"\nNo valid {args.pattern} pattern detected that meets criteria:")
        print(f"  - Pattern confidence >= {args.min_confidence:.0%}")
        print(f"  - Risk:Reward ratio >= 1:{args.min_rr}")
        print(f"\nCurrent market conditions may not favor this setup.")
        print("Try a different pattern or timeframe preference.")


def mode_backtest(args):
    """Run backtest on historical data."""
    if not args.data:
        logger.error("--data required for backtest mode")
        return

    logger.info(f"Running backtest on {args.data}...")

    # Load data
    candles = DataFetcher.load_from_csv(args.data)
    logger.info(f"Loaded {len(candles)} candles")

    # Map pattern
    pattern_map = {
        'engulfing': PatternType.ENGULFING,
        'pin_bar': PatternType.PIN_BAR,
        'morning_star': PatternType.MORNING_STAR,
        'evening_star': PatternType.EVENING_STAR,
        'inside_bar': PatternType.INSIDE_BAR,
    }

    # Initialize strategy
    strategy = CandlestickStrategy(
        pattern_type=pattern_map[args.pattern],
        style=TimeFrameStyle.INTRADAY,
        min_rr_ratio=args.min_rr,
        min_confidence=args.min_confidence
    )

    # Run backtest
    config = BacktestConfig(
        symbol=Path(args.data).stem,
        initial_capital=100_000,
        min_rr_ratio=args.min_rr
    )

    result = strategy.backtest(candles, config)

    # Print results
    print("\n" + str(result))

    # Save detailed results
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Save summary
        with open(output_path, 'w') as f:
            f.write(str(result))

        # Save trades CSV
        trades_path = output_path.parent / (output_path.stem + "_trades.csv")
        with open(trades_path, 'w', newline='') as f:
            import csv
            writer = csv.writer(f)
            writer.writerow(['entry_ts', 'exit_ts', 'pattern', 'direction', 'entry', 'exit', 'pnl', 'bars', 'reason'])

            for trade in result.trades:
                writer.writerow([
                    trade['entry_ts'],
                    trade['exit_ts'],
                    trade['pattern'],
                    trade['direction'],
                    round(trade['entry'], 6),
                    round(trade['exit'], 6),
                    round(trade['pnl'], 2),
                    trade['bars'],
                    trade['reason']
                ])

        logger.info(f"\nResults saved to {output_path}")
        logger.info(f"Trades saved to {trades_path}")


def mode_scan(args):
    """Scan multiple symbols for trading opportunities."""
    if not args.symbols:
        logger.error("--symbols required for scan mode")
        return

    symbols = [s.strip() for s in args.symbols.split(',')]
    logger.info(f"Scanning {len(symbols)} symbols for {args.pattern}...")

    # Map pattern
    pattern_map = {
        'engulfing': PatternType.ENGULFING,
        'pin_bar': PatternType.PIN_BAR,
        'morning_star': PatternType.MORNING_STAR,
        'evening_star': PatternType.EVENING_STAR,
        'inside_bar': PatternType.INSIDE_BAR,
    }

    style_map = {
        'scalping': TimeFrameStyle.SCALPING,
        'intraday': TimeFrameStyle.INTRADAY,
        'swing': TimeFrameStyle.SWING,
    }

    strategy = CandlestickStrategy(
        pattern_type=pattern_map[args.pattern],
        style=style_map[args.style],
        min_rr_ratio=args.min_rr,
        min_confidence=args.min_confidence
    )

    fetcher = DataFetcher(exchange_id="binance", testnet=True)

    style_timeframes = {
        'scalping': ['1m', '5m'],
        'intraday': ['15m', '1h'],
        'swing': ['4h', '1d'],
    }

    timeframes = style_timeframes[args.style]
    opportunities = []

    for symbol in symbols:
        logger.info(f"Scanning {symbol}...")
        try:
            timeframe_data = fetcher.fetch_multiple_timeframes(
                symbol=symbol,
                timeframes=timeframes,
                limit=300
            )

            if timeframe_data:
                idea = strategy.analyze(timeframe_data, symbol)
                if idea:
                    opportunities.append(idea)

        except Exception as e:
            logger.warning(f"Error scanning {symbol}: {e}")

    # Print results
    print("\n" + "=" * 70)
    print(f"SCAN RESULTS - {len(opportunities)} OPPORTUNITIES FOUND")
    print("=" * 70)

    for i, idea in enumerate(opportunities, 1):
        print(f"\n[{i}] {idea.symbol} - {idea.pattern.value.upper()} ({idea.direction.value.upper()})")
        print(f"    Timeframe: {idea.selected_timeframe}")
        print(f"    Entry: ${idea.entry_price:.6f}")
        print(f"    R:R: 1:{idea.rr_ratio:.2f}")
        print(f"    Confidence: {idea.confidence_level}")

    if opportunities and args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        results = {
            'scan_time': datetime.now().isoformat(),
            'pattern': args.pattern,
            'style': args.style,
            'opportunities': [idea.to_dict() for idea in opportunities]
        }

        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)

        logger.info(f"\nScan results saved to {args.output}")


def mode_fetch(args):
    """Fetch and save market data."""
    if not args.output:
        logger.error("--output required for fetch mode")
        return

    logger.info(f"Fetching data for {args.symbol}...")

    fetcher = DataFetcher(exchange_id="binance", testnet=True)

    # Fetch data for all timeframes
    timeframes = ['1m', '5m', '15m', '1h', '4h', '1d']

    for tf in timeframes:
        candles = fetcher.fetch_candles(args.symbol, tf, limit=1000)

        if candles:
            # Save to CSV
            from pathlib import Path
            tf_file = Path(args.output).parent / f"{args.symbol.replace('/', '_')}_{tf}.csv"
            fetcher.save_to_csv(candles, str(tf_file))

    logger.info("Data fetch complete.")


def main():
    """Main entry point."""
    args = parse_args()

    # Create logs directory (already created at top, but ensure exists)
    log_dir = Path(__file__).parent / 'logs'
    log_dir.mkdir(exist_ok=True)

    # Print header
    print("\n" + "=" * 70)
    print("  CANDLESTICK PRO - Pattern Trading System")
    print("=" * 70)
    print(f"  Mode: {args.mode.upper()}")
    print(f"  Pattern: {args.pattern}")
    print(f"  Style: {args.style}")
    print(f"  Min R:R: 1:{args.min_rr}")
    print("=" * 70 + "\n")

    # Route to mode handler
    mode_handlers = {
        'analyze': mode_analyze,
        'backtest': mode_backtest,
        'scan': mode_scan,
        'fetch': mode_fetch,
    }

    handler = mode_handlers.get(args.mode)
    if handler:
        try:
            handler(args)
        except KeyboardInterrupt:
            logger.info("\nInterrupted by user")
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
    else:
        logger.error(f"Unknown mode: {args.mode}")


if __name__ == '__main__':
    main()
