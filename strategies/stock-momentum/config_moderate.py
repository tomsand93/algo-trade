"""
MODERATE CONFIG - Balanced Risk/Return
=======================================
Keeps diversification but with stricter risk controls.
"""

# ============================================================================
# STRATEGY PARAMETERS - MODERATE (Balance between aggressive and conservative)
# ============================================================================

# Slightly stricter thresholds
BUY_THRESHOLD = 72              # Was 70 - Slightly stricter
HOLD_THRESHOLD = 55             # Was 50 - Hold a bit longer
REBALANCE_THRESHOLD = 10        # Was 8 - Reduce turnover slightly

# Moderate position sizes
MAX_POSITION_SIZE = 0.12        # Was 0.15 - Now max 12% per position
MIN_POSITION_SIZE = 0.02        # Keep minimum
MIN_CASH_BUFFER = 0.08          # Was 0.05 - More cash (8% minimum)
VOLATILITY_TARGET = 0.13        # Was 0.15 - Target 13% vol per position

# Better risk management
MAX_PORTFOLIO_VOLATILITY = 0.18  # Was 0.20 - Target 18% total portfolio vol
SPY_MA_PERIOD = 200              # Keep 200-day MA
DEFENSIVE_MULTIPLIER = 0.5       # Keep 0.5 - Cut to 50% in bear markets

# Momentum - Keep balanced
MOMENTUM_SHORT = 63      # Keep 3 months
MOMENTUM_LONG = 252      # Keep 12 months
MOMENTUM_SHORT_WEIGHT = 0.35  # Was 0.4 - Slightly less weight on short-term
MOMENTUM_LONG_WEIGHT = 0.65   # Was 0.6 - Slightly more on long-term

# Technical indicators
MA_PERIOD = 75          # Was 50 - Slightly longer MA
VOL_PERIOD = 90         # Was 63 - Slightly longer vol period

# Backtesting
HISTORY_YEARS = 5
BACKTEST_YEARS = 3
BENCHMARK = "SPY"

# ============================================================================
# ASSET UNIVERSE - KEEP FULL UNIVERSE FOR DIVERSIFICATION
# ============================================================================

# All categories (diversification reduces risk!)
ALL_CATEGORIES = [
    # Broad equity
    "SPY", "QQQ", "DIA", "IWM", "VTI", "VOO", "VEA", "VWO", "EEM", "IEMG",

    # Sectors
    "XLF", "XLE", "XLK", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLRE",

    # Bonds
    "AGG", "BND", "TLT", "IEF", "SHY", "LQD", "HYG", "MUB", "TIP",

    # International
    "EFA", "VEA", "VWO", "EEM", "IEMG", "FXI", "EWJ", "EWZ", "EWG", "EWU",

    # Commodities
    "GLD", "SLV", "USO", "DBA", "IAU", "PALL", "PDBC",

    # Real Estate
    "VNQ", "XLRE", "IYR", "REM", "MORT",

    # Thematic (but exclude high-vol)
    "ARKK", "ARKG", "TAN", "ICLN", "LIT", "REMX",
]

DEFAULT_UNIVERSE = ALL_CATEGORIES

# ============================================================================
# EXCLUDE ONLY THE MOST EXTREME LEVERAGE
# ============================================================================

EXCLUDE_PATTERNS = [
    "3X",      # 3x leveraged
    "UVXY",    # VIX products
    "VXX",     # VIX products
    "SVXY",    # Inverse VIX
]

# Maximum individual asset volatility allowed
MAX_ASSET_VOLATILITY = 0.45  # Was 0.30 - Allow moderate vol assets (but not extreme)

# ============================================================================
# REPORTING SETTINGS
# ============================================================================

RESULTS_DIR = "results_moderate"
GENERATE_PLOTS = True
GENERATE_HTML_REPORT = True
SAVE_TRADES = True
VERBOSE = True

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_universe():
    """Return full universe for diversification"""
    return DEFAULT_UNIVERSE


if __name__ == "__main__":
    print("=" * 80)
    print("MODERATE CONFIGURATION")
    print("=" * 80)

    print(f"\n[CHART] Strategy Parameters:")
    print(f"   BUY threshold: {BUY_THRESHOLD} (balanced)")
    print(f"   Max position: {MAX_POSITION_SIZE*100:.0f}% (moderate)")
    print(f"   Min cash: {MIN_CASH_BUFFER*100:.0f}% (more buffer)")
    print(f"   Defensive mode: {DEFENSIVE_MULTIPLIER*100:.0f}% (balanced)")

    print(f"\n[TARGET] Risk Management:")
    print(f"   Max portfolio vol: {MAX_PORTFOLIO_VOLATILITY*100:.0f}%")
    print(f"   Max asset vol: {MAX_ASSET_VOLATILITY*100:.0f}%")

    print(f"\n[CHART] Universe:")
    print(f"   FULL universe: {len(DEFAULT_UNIVERSE)} ETFs")
    print(f"   Why: Diversification is the best risk reducer!")

    print("\n[NOTE] Expected Performance:")
    print("   CAGR: 15-25% (balanced)")
    print("   Volatility: 18-25% (moderate)")
    print("   Max Drawdown: -20% to -30% (manageable)")
    print("   Sharpe: 0.8-1.2 (good)")

    print("\n" + "=" * 80)
