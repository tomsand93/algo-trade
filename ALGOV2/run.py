"""
Main runner for backtesting framework

Usage:
1. python run.py download     - Download fresh data from Binance
2. python run.py backtest      - Run all backtests
3. python run.py full          - Download data + run backtests
"""
import sys
from data_fetcher import download_all_data
from evaluator import run_evaluation


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python run.py download   - Download fresh data from Binance")
        print("  python run.py backtest   - Run backtests on existing data")
        print("  python run.py full       - Download data + run backtests")
        return

    command = sys.argv[1].lower()

    if command == "download":
        print("\n📥 DOWNLOADING DATA FROM BINANCE")
        print("=" * 70)
        download_all_data()

    elif command == "backtest":
        print("\n🔬 RUNNING BACKTESTS")
        print("=" * 70)
        run_evaluation()

    elif command == "full":
        print("\n📥 STEP 1: DOWNLOADING DATA FROM BINANCE")
        print("=" * 70)
        download_all_data()

        print("\n\n🔬 STEP 2: RUNNING BACKTESTS")
        print("=" * 70)
        run_evaluation()

    else:
        print(f"Unknown command: {command}")
        print("Valid commands: download, backtest, full")


if __name__ == "__main__":
    main()
