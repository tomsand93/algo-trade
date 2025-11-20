# ============================================================
# CONFIGURATION (Assets, Intervals, Risk Levels)
# ============================================================
# API_KEY = "9wy2ahRZd8EhYgTRzGYUER89dyyaUoVC0viqkWWN1eww6rgqJbeD1mQ7yv8igU3c"


API_KEY='8vNLImOkiQ3R6i8LPH9tb1lyJFgek9Z7vnGqlkKACjT0WWeJDyXcmg5ILEmNfxTO'
SECRET_KEY= 'i6vbiaVIDdEMh8qbsqB2VI6TFCM8ltORhi4VED4Yu5nJTgSZkF8mDjptZ7Nd6rss'

TESTNET_API_KEY="Nc1ubJCsyM9P1odUqlFMdcGjNDKiwtmzk6yglxM45KV2yDUBVj3EdZOIo52HjlQ9"
TESTNET_API_SECRET="7PE3SqPxwft1xT4pyAvJ9AXizCPNRDkY7TCWuwWa3kaSwiO9axT7R0gSu87pOFSz"

TESTNET_API_KEY='Nc1ubJCsyM9P1odUqlFMdcGjNDKiwtmzk6yglxM45KV2yDUBVj3EdZOIo52HjlQ9'
TESTNET_API_SECRET='7PE3SqPxwft1xT4pyAvJ9AXizCPNRDkY7TCWuwWa3kaSwiO9axT7R0gSu87pOFSz'

# Crypto assets traded on Binance
CRYPTO_ASSETS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT"
]

# Stocks via yfinance
STOCK_ASSETS = [
    "AAPL",
    "NVDA"
]

# Combined asset list for evaluator.py
ASSETS = CRYPTO_ASSETS + STOCK_ASSETS


# -----------------------------
# INTERVALS
# -----------------------------

# Binance crypto intervals
CRYPTO_INTERVALS = [
    "15m",
    "1h",
    "2h",
    "4h",
    "1d"
]

# YFinance valid intervals
STOCK_INTERVALS = [
    "1h",
    "1d",
    "1wk"
]

INTERVALS = {
    "crypto": CRYPTO_INTERVALS,
    "stocks": STOCK_INTERVALS
}


# -----------------------------
# RISK LEVELS
# -----------------------------

RISK_LEVELS = [0.05, 0.10, 0.20]


# -----------------------------
# BACKTEST SETTINGS
# -----------------------------

START_BALANCE = 1000

MIN_CANDLES_REQUIRED = 200   # ensures stable indicators

# Backtest history range
# crypto: # of candles per interval
CANDLE_LIMITS = {
    "15m": 2000,
    "1h": 2000,
    "2h": 2000,
    "4h": 2000,
    "1d": 2000,
}

# stocks: yfinance period specification
STOCK_HISTORY_PERIOD = "10y"


# -----------------------------
# OUTPUT FOLDERS
# -----------------------------

REPORT_DIR = "reports"
LOG_DIR = "logs"

# ============================
# CONFIGURATION FILE
# ============================

ASSETS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "AAPL",
    "NVDA"
]

# Tested & recommended intervals
INTERVALS = {
    "BTCUSDT": ["15m", "1h", "2h", "4h", "1d"],
    "ETHUSDT": ["15m", "1h", "2h", "4h", "1d"],
    "BNBUSDT": ["15m", "1h", "2h", "4h", "1d"],

    # Stocks use different intervals
    "AAPL": ["1h", "1d", "1wk"],
    "NVDA": ["1h", "1d", "1wk"],
}

# Risk levels
RISK_LEVELS = [0.05, 0.1, 0.2]

# Minimum candles required for backtesting
MIN_CANDLES_REQUIRED = 200

# Where logs and results will be saved
LOG_DIR = "logs"
SUMMARY_EXCEL_PATH = "logs/summary.xlsx"
# Strategies you want to run
STRATEGIES = [
    "RSI",
    "MACD",
    "MOMENTUM",
    "MEAN_REVERSION"
]

from pathlib import Path

# -----------------------------
# DIRECTORIES
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

CRYPTO_LOOKBACK_DAYS = 180

from pathlib import Path

# ============================================================
# DIRECTORIES
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


# ============================================================
# LOOKBACK SETTINGS
# ============================================================
# Crypto uses yfinance — allowed max range for intervals:
# 15m, 1h, 2h, 4h → about 60–730 days depending on interval.
CRYPTO_LOOKBACK_DAYS = 730    # 2 years of crypto

# Stocks: yfinance supports daily/weekly over long periods
STOCK_LOOKBACK = "5y"         # 5 years of stock history


# ============================================================
# ASSETS
# ============================================================
CRYPTO_ASSETS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
STOCK_ASSETS  = ["AAPL", "NVDA"]

ASSETS = CRYPTO_ASSETS + STOCK_ASSETS


# ============================================================
# INTERVALS PER ASSET TYPE
# ============================================================
CRYPTO_INTERVALS = ["15m", "1h", "2h", "4h", "1d"]
STOCK_INTERVALS  = ["1h", "1d", "1wk"]

INTERVALS = {
    **{asset: CRYPTO_INTERVALS for asset in CRYPTO_ASSETS},
    **{asset: STOCK_INTERVALS  for asset in STOCK_ASSETS}
}


# ============================================================
# RISK LEVELS
# ============================================================
RISK_LEVELS = [0.05, 0.10, 0.20]


# ============================================================
# STRATEGIES
# ============================================================
STRATEGIES = ["RSI", "MACD", "MOMENTUM", "MEAN_REVERSION"]


# ============================================================
# BACKTEST CONSTANTS
# ============================================================
MIN_CANDLES_REQUIRED = 300      # minimum candles before running a strategy
START_BALANCE = 1000            # default capital
