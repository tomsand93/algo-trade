"""
Main Runner for Crypto Backtest System

Usage:
    python run.py download              # Download/update data
    python run.py download --force      # Force re-download all
    python run.py backtest              # Run all backtests
    python run.py full                  # Download + backtest
    python run.py stats                 # Show database statistics
    python run.py test                  # Quick test single strategy
"""
import sys
from data_fetcher import download_data
from evaluator import run_evaluation
from database import OHLCVDatabase
from datetime import datetime


def show_stats():
    """Show database statistics"""
    print("=" * 70)
    print("DATABASE STATISTICS")
    print("=" * 70)

    with OHLCVDatabase() as db:
        stats = db.get_stats()

        print(f"\n📊 Overall:")
        print(f"  Total Candles: {stats['total_candles']:,}")
        print(f"  Total Pairs: {stats['total_pairs']}")
        print(f"  Database Size: {stats['db_size_mb']:.2f} MB")

        if stats['top_pairs']:
            print(f"\n📈 Top Pairs by Candle Count:")
            for symbol, timeframe, count in stats['top_pairs']:
                print(f"  {symbol:12} {timeframe:4} → {count:,} candles")

        print(f"\n📁 All Pairs:")
        all_pairs = db.get_all_pairs()
        for symbol, timeframe in sorted(all_pairs):
            metadata = db.get_metadata(symbol, timeframe)
            if metadata:
                last_update = datetime.fromtimestamp(metadata['last_update'] / 1000)
                print(f"  {symbol:12} {timeframe:4} → {metadata['num_candles']:6,} candles (updated: {last_update:%Y-%m-%d %H:%M})")

    print("\n" + "=" * 70)


def quick_test():
    """Quick test of single strategy"""
    from test_strategy import test_strategy
    test_strategy()


def show_help():
    """Show help message"""
    print("\n" + "=" * 70)
    print("CRYPTO BACKTEST SYSTEM")
    print("=" * 70)
    print("\nUsage:")
    print("  python run.py download         - Download/update data (smart incremental)")
    print("  python run.py download --force - Force re-download all data")
    print("  python run.py backtest         - Run all backtests")
    print("  python run.py full             - Download + backtest")
    print("  python run.py stats            - Show database statistics")
    print("  python run.py test             - Quick test single strategy")
    print("  python run.py help             - Show this help")
    print("\nExamples:")
    print("  # First time setup")
    print("  python run.py download")
    print("")
    print("  # Daily workflow")
    print("  python run.py download    # Updates only new candles (30 sec)")
    print("  python run.py backtest    # Run all strategies")
    print("")
    print("  # Full pipeline")
    print("  python run.py full")
    print("\n" + "=" * 70 + "\n")


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        show_help()
        return

    command = sys.argv[1].lower()
    force = '--force' in sys.argv

    if command == "download":
        if force:
            print("\n⚠️  FORCE REFRESH MODE")
            print("This will re-download ALL historical data")
            print("=" * 70 + "\n")

        download_data(force=force)

    elif command == "backtest":
        print("\n🔬 RUNNING BACKTESTS")
        print("=" * 70 + "\n")
        run_evaluation()

    elif command == "full":
        if force:
            print("\n⚠️  FORCE REFRESH MODE")
            print("=" * 70 + "\n")

        print("\n📥 STEP 1: DOWNLOAD/UPDATE DATA")
        print("=" * 70 + "\n")
        download_data(force=force)

        print("\n\n🔬 STEP 2: RUN BACKTESTS")
        print("=" * 70 + "\n")
        run_evaluation()

    elif command == "stats":
        show_stats()

    elif command == "test":
        quick_test()

    elif command == "help":
        show_help()

    else:
        print(f"\n❌ Unknown command: {command}")
        show_help()


if __name__ == "__main__":
    main()
