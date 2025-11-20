"""
Enhanced Main Runner with Database Support

Usage:
1. python run_v2.py download     - Download/update data (incremental)
2. python run_v2.py backtest      - Run all backtests
3. python run_v2.py full          - Download + backtest
4. python run_v2.py download --force  - Force re-download all data
5. python run_v2.py stats         - Show database statistics
"""
import sys
from data_fetcher_v2 import BinanceDataFetcherV2, download_all_data
from evaluator_v2 import run_evaluation
from database import OHLCVDatabase


def show_stats():
    """Show database statistics"""
    print("=" * 70)
    print("DATABASE STATISTICS")
    print("=" * 70)

    db = OHLCVDatabase()
    stats = db.get_stats()

    print(f"\n📊 Overall Stats:")
    print(f"  Total Candles: {stats['total_candles']:,}")
    print(f"  Total Symbol/Timeframe Pairs: {stats['total_pairs']}")

    if stats['top_pairs']:
        print(f"\n📈 Top 10 Pairs by Candle Count:")
        for i, (symbol, timeframe, count) in enumerate(stats['top_pairs'], 1):
            print(f"  {i:2}. {symbol:12} {timeframe:4} → {count:,} candles")

    # Get all symbols
    all_pairs = db.get_all_symbols()
    print(f"\n📁 All Stored Pairs:")
    for symbol, timeframe in sorted(all_pairs):
        metadata = db.get_metadata(symbol, timeframe)
        if metadata:
            from datetime import datetime
            last_update = datetime.fromtimestamp(metadata['last_update'] / 1000)
            print(f"  {symbol:12} {timeframe:4} → {metadata['num_candles']:6,} candles (updated: {last_update:%Y-%m-%d %H:%M})")

    # Database file size
    db_size = db.db_path.stat().st_size
    size_mb = db_size / (1024 * 1024)
    print(f"\n💾 Database File:")
    print(f"  Path: {db.db_path}")
    print(f"  Size: {size_mb:.2f} MB")

    db.close()

    print("\n" + "=" * 70)


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python run_v2.py download         - Download/update data (smart incremental)")
        print("  python run_v2.py download --force - Force re-download all data")
        print("  python run_v2.py backtest         - Run backtests on existing data")
        print("  python run_v2.py full             - Download + backtest")
        print("  python run_v2.py stats            - Show database statistics")
        return

    command = sys.argv[1].lower()
    force = '--force' in sys.argv

    if command == "download":
        if force:
            print("\n⚠️  FORCE REFRESH MODE")
            print("This will re-download ALL historical data")
            print("=" * 70)

        print("\n📥 DOWNLOADING/UPDATING DATA FROM BINANCE")
        print("=" * 70)
        download_all_data(force_refresh=force)

    elif command == "backtest":
        print("\n🔬 RUNNING BACKTESTS (Database Mode)")
        print("=" * 70)
        run_evaluation()

    elif command == "full":
        if force:
            print("\n⚠️  FORCE REFRESH MODE")
            print("=" * 70)

        print("\n📥 STEP 1: DOWNLOADING/UPDATING DATA")
        print("=" * 70)
        download_all_data(force_refresh=force)

        print("\n\n🔬 STEP 2: RUNNING BACKTESTS")
        print("=" * 70)
        run_evaluation()

    elif command == "stats":
        show_stats()

    else:
        print(f"Unknown command: {command}")
        print("Valid commands: download, backtest, full, stats")


if __name__ == "__main__":
    main()
