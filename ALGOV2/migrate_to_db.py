"""
Migration Script: CSV to SQLite Database

Migrates existing CSV files to the new SQLite database.
Run this once to convert your historical data.
"""
import sys
from pathlib import Path
import config
from database import OHLCVDatabase
from data_fetcher import BinanceDataFetcher


def migrate_csv_to_database():
    """Migrate all existing CSV files to database"""

    print("=" * 70)
    print("MIGRATION: CSV FILES → SQLite DATABASE")
    print("=" * 70)

    # Check if CSV files exist
    csv_files = list(config.DATA_DIR.glob("*.csv"))

    if not csv_files:
        print("\n❌ No CSV files found in data/ directory")
        print("   Nothing to migrate!")
        print("\n💡 Run 'python run.py download' to fetch data")
        return

    print(f"\nFound {len(csv_files)} CSV files to migrate")
    print("\nThis will:")
    print("  ✓ Create SQLite database (data/ohlcv.db)")
    print("  ✓ Import all CSV data into database")
    print("  ✓ Keep original CSV files (safe backup)")
    print()

    # Ask for confirmation
    if '--auto' not in sys.argv:
        response = input("Continue? [Y/n]: ").strip().lower()
        if response and response != 'y' and response != 'yes':
            print("Migration cancelled")
            return

    # Initialize database
    db = OHLCVDatabase()
    fetcher = BinanceDataFetcher(use_testnet=False)

    print("\n" + "=" * 70)
    print("MIGRATING DATA")
    print("=" * 70)

    migrated = 0
    skipped = 0

    for asset in config.CRYPTO_ASSETS:
        if asset.endswith('USDT'):
            symbol = f"{asset[:-4]}/USDT"
        else:
            symbol = asset

        for timeframe in config.CRYPTO_INTERVALS:
            # Try to load CSV
            df = fetcher.load_from_csv(symbol, timeframe)

            if df is None or df.empty:
                skipped += 1
                continue

            print(f"Migrating: {symbol} {timeframe} ({len(df)} candles)...")

            # Save to database
            db.save_ohlcv(df, symbol, timeframe)
            migrated += 1

    print("\n" + "=" * 70)
    print("MIGRATION COMPLETE")
    print("=" * 70)
    print(f"✓ Migrated: {migrated} pairs")
    print(f"⊘ Skipped: {skipped} pairs (no CSV data)")

    # Show database stats
    stats = db.get_stats()
    print(f"\nDatabase Statistics:")
    print(f"  Total Candles: {stats['total_candles']:,}")
    print(f"  Total Pairs: {stats['total_pairs']}")
    print(f"  Database Size: {_get_db_size(db.db_path)}")

    print("\n✓ You can now use the new database-enabled system!")
    print("  Use: python run_v2.py download")
    print("       python run_v2.py backtest")

    db.close()


def _get_db_size(db_path):
    """Get human-readable database file size"""
    if not db_path.exists():
        return "0 B"

    size_bytes = db_path.stat().st_size

    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0

    return f"{size_bytes:.1f} TB"


if __name__ == "__main__":
    migrate_csv_to_database()
