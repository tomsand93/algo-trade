"""
CONSERVATIVE CONFIG - Lower Volatility, Smaller Drawdowns
==========================================================
Use this for realistic, tradeable performance.
"""

# ============================================================================
# STRATEGY PARAMETERS - CONSERVATIVE
# ============================================================================

# Higher thresholds = fewer trades, less churn
BUY_THRESHOLD = 75              # Was 70 - Now stricter
HOLD_THRESHOLD = 60             # Was 50 - Hold longer
REBALANCE_THRESHOLD = 12        # Was 8 - Only rebalance on big changes

# Smaller positions = lower concentration risk
MAX_POSITION_SIZE = 0.10        # Was 0.15 - Now max 10% per position
MIN_POSITION_SIZE = 0.02        # Was 0.02 - Keep minimum
MIN_CASH_BUFFER = 0.10          # Was 0.05 - More cash (10% minimum)
VOLATILITY_TARGET = 0.12        # Was 0.15 - Target 12% vol per position

# Stricter risk management
MAX_PORTFOLIO_VOLATILITY = 0.15  # Was 0.20 - Target 15% total portfolio vol
SPY_MA_PERIOD = 200              # Keep 200-day MA
DEFENSIVE_MULTIPLIER = 0.3       # Was 0.5 - Cut to 30% in bear markets (more defensive)

# Momentum - Favor longer-term (more stable)
MOMENTUM_SHORT = 126   # Was 63 - Now 6 months instead of 3
MOMENTUM_LONG = 252    # Keep 12 months
MOMENTUM_SHORT_WEIGHT = 0.3  # Was 0.4 - Less weight on short-term
MOMENTUM_LONG_WEIGHT = 0.7   # Was 0.6 - More weight on long-term

# Technical indicators
MA_PERIOD = 100        # Was 50 - Longer MA (more stable)
VOL_PERIOD = 126       # Was 63 - Longer vol period (6 months)

# Backtesting
HISTORY_YEARS = 5
BACKTEST_YEARS = 3
BENCHMARK = "SPY"

# ============================================================================
# ASSET UNIVERSE - CONSERVATIVE (Exclude High-Vol Assets)
# ============================================================================

# Conservative universe - only large, liquid, stable ETFs
CONSERVATIVE_UNIVERSE = [
    # Broad equity (stable large-caps only)
    "SPY", "VOO", "IVV",    # S&P 500 (all track same index)
    "VTI", "ITOT",          # Total market

    # Bonds (defensive)
    "AGG", "BND",           # Aggregate bonds
    "TLT", "IEF", "SHY",    # Treasuries (long, mid, short)
    "LQD",                  # Investment-grade corporate

    # Defensive sectors only
    "XLP",                  # Consumer staples
    "XLU",                  # Utilities
    "XLV",                  # Healthcare

    # Commodities (gold only, no silver/commodities)
    "GLD", "IAU",           # Gold
]

# Override default universe with conservative
DEFAULT_UNIVERSE = CONSERVATIVE_UNIVERSE

# ============================================================================
# EXCLUDE HIGH-VOLATILITY ASSETS
# ============================================================================

# These will be filtered out during universe building
EXCLUDE_PATTERNS = [
    "3X",      # 3x leveraged
    "2X",      # 2x leveraged
    "UVXY",    # VIX products
    "VXX",     # VIX products
    "SVXY",    # Inverse VIX
    "SQQQ",    # 3x inverse
    "TQQQ",    # 3x leveraged
    "UPRO",    # 3x leveraged
    "SPXU",    # 3x inverse
]

# Asset categories to exclude
EXCLUDE_CATEGORIES = [
    "volatility",       # VIX products
    "leveraged",        # Leveraged ETFs
    "inverse",          # Inverse ETFs
]

# Maximum individual asset volatility allowed
MAX_ASSET_VOLATILITY = 0.30  # Exclude anything >30% annual vol

# ============================================================================
# REPORTING SETTINGS
# ============================================================================

RESULTS_DIR = "results_conservative"
GENERATE_PLOTS = True
GENERATE_HTML_REPORT = True
SAVE_TRADES = True
VERBOSE = True

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_universe(mode="conservative"):
    """Always return conservative universe"""
    return CONSERVATIVE_UNIVERSE


def is_high_volatility_asset(ticker):
    """Check if asset should be excluded due to high volatility"""
    ticker_upper = ticker.upper()

    # Check against exclusion patterns
    for pattern in EXCLUDE_PATTERNS:
        if pattern in ticker_upper:
            return True

    return False


if __name__ == "__main__":
    print("=" * 80)
    print("CONSERVATIVE CONFIGURATION")
    print("=" * 80)

    print(f"\n📊 Strategy Parameters:")
    print(f"   BUY threshold: {BUY_THRESHOLD} (stricter)")
    print(f"   HOLD threshold: {HOLD_THRESHOLD} (hold longer)")
    print(f"   Max position: {MAX_POSITION_SIZE*100:.0f}% (smaller)")
    print(f"   Min cash: {MIN_CASH_BUFFER*100:.0f}% (more cash)")

    print(f"\n⚙️  Momentum Settings:")
    print(f"   Short-term: {MOMENTUM_SHORT} days (6 months)")
    print(f"   Long-term: {MOMENTUM_LONG} days (12 months)")
    print(f"   Short weight: {MOMENTUM_SHORT_WEIGHT*100:.0f}%")
    print(f"   Long weight: {MOMENTUM_LONG_WEIGHT*100:.0f}%")

    print(f"\n🛡️  Risk Management:")
    print(f"   Max portfolio vol: {MAX_PORTFOLIO_VOLATILITY*100:.0f}% (lower)")
    print(f"   Defensive multiplier: {DEFENSIVE_MULTIPLIER*100:.0f}% (more defensive)")
    print(f"   Max asset vol: {MAX_ASSET_VOLATILITY*100:.0f}%")

    print(f"\n📂 Universe:")
    print(f"   Conservative ETFs: {len(CONSERVATIVE_UNIVERSE)}")
    for etf in CONSERVATIVE_UNIVERSE:
        print(f"      {etf}")

    print(f"\n🚫 Excluded:")
    print(f"   High-vol patterns: {', '.join(EXCLUDE_PATTERNS[:5])}...")

    print("\n💡 Expected Performance:")
    print("   CAGR: 8-15% (vs 115% aggressive)")
    print("   Volatility: 12-18% (vs 77% aggressive)")
    print("   Max Drawdown: -15% to -25% (vs -66% aggressive)")
    print("   Sharpe: 0.6-1.0")

    print("\n" + "=" * 80)
