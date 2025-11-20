"""
Configuration for Crypto Trading Backtesting System
"""
from pathlib import Path
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============================================================
# DIRECTORIES
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
STRATEGIES_DIR = BASE_DIR / "strategies"

# Create directories if they don't exist
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
STRATEGIES_DIR.mkdir(exist_ok=True)

# ============================================================
# API CREDENTIALS (Load from .env for security)
# ============================================================
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY', '')

BINANCE_TESTNET_API_KEY = os.getenv('BINANCE_TESTNET_API_KEY', '')
BINANCE_TESTNET_SECRET_KEY = os.getenv('BINANCE_TESTNET_SECRET_KEY', '')

# ============================================================
# TRADING PAIRS
# ============================================================
CRYPTO_ASSETS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "ADAUSDT",
]

# ============================================================
# TIMEFRAMES
# ============================================================
CRYPTO_INTERVALS = [
    "5m",    # 5 minutes
    "15m",   # 15 minutes
    "1h",    # 1 hour
    "4h",    # 4 hours
    "1d",    # 1 day
]

# ============================================================
# RISK LEVELS (Position Sizing)
# ============================================================
RISK_LEVELS = [0.05, 0.10, 0.20]  # 5%, 10%, 20% of capital per trade

# ============================================================
# BACKTESTING PARAMETERS
# ============================================================
INITIAL_CAPITAL = 10000           # Starting capital in USD
COMMISSION = 0.001                 # 0.1% trading fee (Binance standard)
SLIPPAGE = 0.0005                  # 0.05% slippage
MIN_CANDLES_REQUIRED = 300         # Minimum candles needed for backtest

# ============================================================
# DATA FETCHING SETTINGS
# ============================================================
LOOKBACK_DAYS = 730                # Days of historical data (2 years)
MAX_DATA_AGE_HOURS = 1             # Max age before data is considered stale

# ============================================================
# STRATEGIES TO TEST
# ============================================================
STRATEGIES = [
    "RSI",
    "MACD",
    "BOLLINGER_BANDS",
    "SMA_CROSSOVER",
    "EMA_CROSSOVER",
    "MEAN_REVERSION",
    "MOMENTUM",
    "VWAP",
    "BREAKOUT",
    "TRIPLE_EMA",
]

# ============================================================
# OUTPUT SETTINGS
# ============================================================
EXCEL_REPORT_PATH = LOG_DIR / "backtest_results.xlsx"
JSON_REPORT_PATH = LOG_DIR / "backtest_results.json"
SUMMARY_REPORT_PATH = LOG_DIR / "summary.txt"

# ============================================================
# DATABASE SETTINGS
# ============================================================
DATABASE_PATH = DATA_DIR / "ohlcv.db"
USE_DATABASE = True  # Set to False to use CSV files instead
