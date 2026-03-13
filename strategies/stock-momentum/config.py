"""
STOCK MOMENTUM STRATEGY - CONFIGURATION
========================================
Multi-asset momentum strategy with volatility-based position sizing.
Improved version of Simple_analist with expanded universe and risk management.
"""

# ============================================================================
# STRATEGY PARAMETERS
# ============================================================================

# Scoring thresholds (0-100 scale)
BUY_THRESHOLD = 70      # Score >= 70 → BUY
HOLD_THRESHOLD = 50     # Score >= 50 → HOLD (keep if already in)
                        # Score < 50 → SELL

# Rebalancing
REBALANCE_THRESHOLD = 8  # Only rebalance if score changes by >8 points (reduces turnover)

# Position sizing
MAX_POSITION_SIZE = 0.15        # 15% maximum per position
MIN_POSITION_SIZE = 0.02        # 2% minimum per position
MIN_CASH_BUFFER = 0.05          # 5% minimum cash reserve
VOLATILITY_TARGET = 0.15        # 15% annualized target volatility per position

# Risk management
MAX_PORTFOLIO_VOLATILITY = 0.20  # 20% max portfolio volatility
SPY_MA_PERIOD = 200              # Market regime filter: SPY 200-day MA
DEFENSIVE_MULTIPLIER = 0.5       # Cut positions by 50% when SPY < 200MA

# Momentum calculation periods (trading days)
MOMENTUM_SHORT = 63   # 3 months (~63 trading days)
MOMENTUM_LONG = 252   # 12 months (~252 trading days)
MOMENTUM_SHORT_WEIGHT = 0.4
MOMENTUM_LONG_WEIGHT = 0.6

# Technical indicators
MA_PERIOD = 50        # Moving average period for trend detection
VOL_PERIOD = 63       # Volatility lookback (3 months)

# Backtesting
HISTORY_YEARS = 5      # Years of data to download
BACKTEST_YEARS = 3     # Years to backtest
BENCHMARK = "SPY"      # Performance benchmark

# ============================================================================
# ASSET UNIVERSE - COMPREHENSIVE ETF SELECTION
# ============================================================================

# Each category provides diversification across different factors/sectors
# Choose 30-50 symbols total for optimal diversification without over-complexity

ETF_UNIVERSE = {

    # ========================================================================
    # BROAD MARKET EQUITY (Core holdings)
    # ========================================================================
    "SPY": {
        "name": "S&P 500",
        "category": "broad_equity",
        "description": "Large-cap US stocks"
    },
    "QQQ": {
        "name": "Nasdaq 100",
        "category": "broad_equity",
        "description": "Tech-heavy large-cap"
    },
    "IWM": {
        "name": "Russell 2000",
        "category": "broad_equity",
        "description": "Small-cap US stocks"
    },
    "VTI": {
        "name": "Total Stock Market",
        "category": "broad_equity",
        "description": "Entire US equity market"
    },
    "DIA": {
        "name": "Dow Jones",
        "category": "broad_equity",
        "description": "30 blue-chip stocks"
    },

    # ========================================================================
    # SECTOR ROTATION (Tactical opportunities)
    # ========================================================================
    "XLK": {
        "name": "Technology",
        "category": "sector",
        "description": "Tech sector"
    },
    "XLF": {
        "name": "Financials",
        "category": "sector",
        "description": "Banks, insurance, brokers"
    },
    "XLE": {
        "name": "Energy",
        "category": "sector",
        "description": "Oil, gas, energy"
    },
    "XLV": {
        "name": "Healthcare",
        "category": "sector",
        "description": "Pharma, biotech, healthcare"
    },
    "XLI": {
        "name": "Industrials",
        "category": "sector",
        "description": "Manufacturing, defense"
    },
    "XLY": {
        "name": "Consumer Discretionary",
        "category": "sector",
        "description": "Retail, autos, leisure"
    },
    "XLP": {
        "name": "Consumer Staples",
        "category": "sector",
        "description": "Food, beverages, household"
    },
    "XLU": {
        "name": "Utilities",
        "category": "sector",
        "description": "Electric, gas, water"
    },
    "XLB": {
        "name": "Materials",
        "category": "sector",
        "description": "Chemicals, metals, mining"
    },
    "XLRE": {
        "name": "Real Estate",
        "category": "sector",
        "description": "REITs, property"
    },

    # ========================================================================
    # THEMATIC / GROWTH (High momentum potential)
    # ========================================================================
    "ARKK": {
        "name": "ARK Innovation",
        "category": "thematic",
        "description": "Disruptive innovation"
    },
    "ARKG": {
        "name": "ARK Genomic",
        "category": "thematic",
        "description": "Genomic revolution"
    },
    "ARKQ": {
        "name": "ARK Autonomous Tech",
        "category": "thematic",
        "description": "Robotics, AI, autonomous"
    },
    "SOXX": {
        "name": "Semiconductors",
        "category": "thematic",
        "description": "Chip manufacturers"
    },
    "SMH": {
        "name": "Semiconductor ETF",
        "category": "thematic",
        "description": "Semiconductor companies"
    },
    "CLOU": {
        "name": "Cloud Computing",
        "category": "thematic",
        "description": "Cloud infrastructure"
    },
    "FINX": {
        "name": "Fintech",
        "category": "thematic",
        "description": "Financial technology"
    },
    "HACK": {
        "name": "Cybersecurity",
        "category": "thematic",
        "description": "Cybersecurity companies"
    },
    "TAN": {
        "name": "Solar Energy",
        "category": "thematic",
        "description": "Solar power"
    },
    "ICLN": {
        "name": "Clean Energy",
        "category": "thematic",
        "description": "Renewable energy"
    },
    "LIT": {
        "name": "Lithium & Battery",
        "category": "thematic",
        "description": "Battery tech, lithium"
    },
    "DRIV": {
        "name": "Autonomous Vehicles",
        "category": "thematic",
        "description": "Self-driving cars"
    },

    # ========================================================================
    # INTERNATIONAL EQUITY (Diversification)
    # ========================================================================
    "EFA": {
        "name": "EAFE (Developed Intl)",
        "category": "international",
        "description": "Europe, Australia, Far East"
    },
    "EEM": {
        "name": "Emerging Markets",
        "category": "international",
        "description": "China, India, Brazil, etc."
    },
    "FXI": {
        "name": "China Large-Cap",
        "category": "international",
        "description": "Chinese stocks"
    },
    "EWJ": {
        "name": "Japan",
        "category": "international",
        "description": "Japanese stocks"
    },
    "EWZ": {
        "name": "Brazil",
        "category": "international",
        "description": "Brazilian stocks"
    },

    # ========================================================================
    # FIXED INCOME (Defensive holdings)
    # ========================================================================
    "TLT": {
        "name": "Long-Term Treasuries",
        "category": "bonds",
        "description": "20+ year US bonds"
    },
    "IEF": {
        "name": "Mid-Term Treasuries",
        "category": "bonds",
        "description": "7-10 year US bonds"
    },
    "SHY": {
        "name": "Short-Term Treasuries",
        "category": "bonds",
        "description": "1-3 year US bonds"
    },
    "AGG": {
        "name": "Aggregate Bonds",
        "category": "bonds",
        "description": "US investment-grade bonds"
    },
    "LQD": {
        "name": "Corporate Bonds",
        "category": "bonds",
        "description": "Investment-grade corporate"
    },
    "HYG": {
        "name": "High-Yield Bonds",
        "category": "bonds",
        "description": "Junk bonds"
    },
    "TIP": {
        "name": "TIPS",
        "category": "bonds",
        "description": "Inflation-protected bonds"
    },

    # ========================================================================
    # COMMODITIES & ALTERNATIVES (Inflation hedge)
    # ========================================================================
    "GLD": {
        "name": "Gold",
        "category": "commodity",
        "description": "Physical gold"
    },
    "SLV": {
        "name": "Silver",
        "category": "commodity",
        "description": "Physical silver"
    },
    "USO": {
        "name": "Oil (WTI)",
        "category": "commodity",
        "description": "Crude oil futures"
    },
    "DBC": {
        "name": "Commodities Basket",
        "category": "commodity",
        "description": "Diversified commodities"
    },
    "PDBC": {
        "name": "Optimized Commodity",
        "category": "commodity",
        "description": "Optimized commodity basket"
    },

    # ========================================================================
    # VOLATILITY & HEDGE (Portfolio protection)
    # ========================================================================
    "VIXY": {
        "name": "VIX Short-Term",
        "category": "volatility",
        "description": "VIX futures (hedge)"
    },

}

# ============================================================================
# UNIVERSE FILTERS
# ============================================================================

# Default universe (balanced selection)
DEFAULT_UNIVERSE = [
    # Broad market
    "SPY", "QQQ", "IWM", "VTI",
    # Sectors (all 11)
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE",
    # Thematic (high growth)
    "ARKK", "SOXX", "SMH", "CLOU", "HACK", "TAN", "ICLN", "LIT",
    # International
    "EFA", "EEM", "FXI",
    # Bonds (defensive)
    "TLT", "IEF", "AGG", "LQD", "TIP",
    # Commodities
    "GLD", "SLV", "DBC",
]

# Top 500 common stocks + User's custom stocks (546 total)
TOP_500_COMMON_STOCKS = ['AAON', 'AAPL', 'ABVX', 'ACAD', 'ACEL', 'ACLX', 'ADBE', 'ADC', 'ADPT', 'ADT', 'AEE', 'AGIO', 'AGRO', 'AHCO', 'AHH', 'AHL', 'AIOT', 'AIV', 'ALEX', 'ALGM', 'ALH', 'ALKS', 'ALKT', 'AMAT', 'AMD', 'AME', 'AMG', 'AMPH', 'AMZN', 'AOS', 'APG', 'APO', 'ARCO', 'ARI', 'ARKO', 'ARLO', 'AROC', 'ARX', 'AS', 'ASB', 'ASH', 'ASML', 'ASO', 'ATRC', 'ATXS', 'AUB', 'AUPH', 'AVDL', 'AVGO', 'AVNS', 'AVNT', 'AVY', 'AWK', 'AXS', 'AXTA', 'AYI', 'AZTA', 'BAC', 'BBAI', 'BBNX', 'BCC', 'BEPC', 'BHC', 'BHVN', 'BL', 'BLSH', 'BRSL', 'BTSG', 'CAH', 'CBRE', 'CBZ', 'CCJ', 'CCK', 'CDNA', 'CELC', 'CEPT', 'CFFN', 'CGON', 'CHA', 'CHD', 'CHDN', 'CHEF', 'CHH', 'CIM', 'CIVI', 'CLH', 'CLMT', 'CMC', 'CMPS', 'CMRE', 'CNX', 'CNXC', 'COCO', 'COLB', 'COST', 'CPNG', 'CRI', 'CRL', 'CROX', 'CRUS', 'CRWD', 'CSTM', 'CTAS', 'CTOS', 'CTVA', 'CURB', 'CVBF', 'CVI', 'CVLT', 'CVX', 'CWH', 'CWK', 'CYRX', 'DAN', 'DBI', 'DC', 'DCI', 'DENN', 'DEO', 'DGX', 'DHT', 'DKNG', 'DNTH', 'DOCN', 'DOV', 'DPZ', 'DRI', 'DRTS', 'DRVN', 'DT', 'DTM', 'DV', 'DVA', 'DVS', 'EA', 'EBC', 'EC', 'ECVT', 'EE', 'EFC', 'EH', 'EHC', 'EIG', 'ELS', 'ELVN', 'ENOV', 'EOLS', 'ESLT', 'ESTC', 'EVTL', 'EWTX', 'EXPD', 'EYPT', 'FA', 'FANG', 'FBIN', 'FFBC', 'FHB', 'FIGS', 'FIHL', 'FIVN', 'FLS', 'FMX', 'FN', 'FOXA', 'FROG', 'FTS', 'FUL', 'FULC', 'FWONK', 'FWRD', 'FWRG', 'G', 'GBTG', 'GBX', 'GCMG', 'GD', 'GDOT', 'GEO', 'GES', 'GGG', 'GH', 'GIL', 'GKOS', 'GLXY', 'GNRC', 'GO', 'GOOGL', 'GPC', 'GPRK', 'GRAL', 'GRND', 'GRPN', 'GS', 'GSIT', 'GTLS', 'HAE', 'HAFN', 'HBAN', 'HCSG', 'HELE', 'HESM', 'HI', 'HIG', 'HNGE', 'HOMB', 'HOPE', 'HQY', 'HRMY', 'HTBK', 'HTLD', 'IAC', 'ICL', 'IEX', 'ILMN', 'IMVT', 'INTA', 'INTC', 'INVX', 'IONS', 'IQV', 'IRM', 'IRON', 'ITRI', 'ITUB', 'J', 'JACK', 'JANX', 'JBI', 'JHG', 'JNJ', 'JPM', 'KEX', 'KEYS', 'KGS', 'KLAC', 'KLIC', 'KNSA', 'KO', 'KRC', 'KT', 'LAND', 'LBRDK', 'LBTYA', 'LBTYK', 'LCFY', 'LDOS', 'LEG', 'LFST', 'LFUS', 'LH', 'LIF', 'LILAK', 'LINC', 'LIND', 'LLY', 'LMND', 'LMT', 'LNC', 'LPX', 'LSCC', 'LSPD', 'LTH', 'LXEO', 'LZ', 'LZB', 'MA', 'MAC', 'MAIN', 'MAN', 'MANH', 'MARA', 'MASI', 'MC', 'MCK', 'META', 'MFIC', 'MGNI', 'MIAX', 'MIDD', 'MIRM', 'MKTX', 'MLI', 'MLTX', 'MLYS', 'MMI', 'MMSI', 'MNRO', 'MNSO', 'MOH', 'MPLX', 'MRTN', 'MRVL', 'MRX', 'MS', 'MSFT', 'MSI', 'MSM', 'MTN', 'MTRX', 'MTUS', 'MU', 'MWA', 'NAMS', 'NEE', 'NET', 'NEXA', 'NFLX', 'NICE', 'NIQ', 'NMAX', 'NNN', 'NOC', 'NOK', 'NOV', 'NOVT', 'NOW', 'NVDA', 'NVMI', 'NVRI', 'NWBI', 'NYT', 'OBE', 'OC', 'OGE', 'OI', 'OII', 'OIS', 'OKTA', 'OLLI', 'OMCL', 'OMF', 'ONDS', 'OPFI', 'ORA', 'ORCL', 'OSG', 'OSK', 'OUT', 'OXM', 'PACS', 'PAII', 'PANW', 'PATK', 'PAYC', 'PB', 'PCRX', 'PCVX', 'PEGA', 'PELI', 'PEP', 'PFG', 'PFS', 'PG', 'PGNY', 'PH', 'PI', 'PKG', 'PLTR', 'PLYM', 'PNNT', 'POOL', 'POST', 'PPL', 'PRCH', 'PRCT', 'PRKS', 'PRMB', 'PRTA', 'PRVA', 'PSA', 'PSBD', 'PSMT', 'PSN', 'PSNL', 'PTGX', 'PTRN', 'PUBM', 'QCOM', 'QDEL', 'QLYS', 'QTWO', 'RARE', 'RCUS', 'REG', 'RELX', 'RERE', 'RES', 'REYN', 'REZI', 'RF', 'RGEN', 'RGLD', 'RH', 'RHI', 'RIOT', 'RKT', 'RLI', 'RNA', 'ROAD', 'RPM', 'RPRX', 'RRX', 'RSG', 'RSI', 'RTX', 'RVTY', 'RYAN', 'RYTM', 'SAIL', 'SB', 'SBAC', 'SBCF', 'SBH', 'SCI', 'SFD', 'SGHC', 'SGHT', 'SGML', 'SGRY', 'SHC', 'SHCO', 'SHO', 'SHOO', 'SIG', 'SITC', 'SITE', 'SKM', 'SKT', 'SLB', 'SLG', 'SLGN', 'SLM', 'SMA', 'SMCI', 'SMPL', 'SMTC', 'SNCY', 'SNDX', 'SNOW', 'SOLV', 'SON', 'SPG', 'SPXC', 'SQ', 'SRRK', 'SSNC', 'ST', 'STEL', 'STT', 'STVN', 'STZ', 'SUPV', 'SVRA', 'SWIM', 'SWK', 'SWX', 'TCOM', 'TDS', 'TEL', 'TENB', 'TEVA', 'TEX', 'TFX', 'TGNA', 'TGT', 'THO', 'TILE', 'TK', 'TKO', 'TLK', 'TOL', 'TOWN', 'TPG', 'TRN', 'TRVI', 'TSLA', 'TSM', 'TSSI', 'TTC', 'TTWO', 'TXN', 'TXT', 'UGI', 'ULS', 'UMH', 'UNFI', 'UPB', 'UPBD', 'UPWK', 'URBN', 'UTZ', 'V', 'VAL', 'VALE', 'VC', 'VERA', 'VERO', 'VIA', 'VITL', 'VIV', 'VLRS', 'VMC', 'VNDA', 'VNOM', 'VNT', 'VOYG', 'VRDN', 'VRNS', 'VRSN', 'VSCO', 'VSTS', 'VVV', 'VYX', 'VZ', 'WAB', 'WAL', 'WAY', 'WBI', 'WCC', 'WES', 'WEX', 'WGO', 'WGS', 'WH', 'WHD', 'WIX', 'WLK', 'WMG', 'WMT', 'WNC', 'WOLF', 'WPC', 'WSM', 'WTRG', 'WULF', 'WYNN', 'XENE', 'XOM', 'XPO', 'XYL', 'YALA', 'YEXT', 'ZLAB', 'ZS', 'ZVRA']

# Conservative universe (lower volatility)
CONSERVATIVE_UNIVERSE = [
    "SPY", "VTI", "DIA",
    "XLV", "XLP", "XLU", "XLRE",
    "TLT", "IEF", "AGG", "LQD", "TIP",
    "GLD",
]

# Aggressive universe (high volatility, high returns)
AGGRESSIVE_UNIVERSE = [
    "QQQ", "IWM",
    "XLK", "XLE", "XLF", "XLI",
    "ARKK", "ARKG", "ARKQ", "SOXX", "SMH", "CLOU", "HACK",
    "EEM", "FXI", "EWZ",
    "HYG", "LIT", "TAN", "ICLN",
]

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_universe(mode="default"):
    """
    Get ticker list for specified universe mode.

    Args:
        mode: "default", "conservative", "aggressive", or "all"

    Returns:
        List of ticker symbols
    """
    if mode == "conservative":
        return CONSERVATIVE_UNIVERSE
    elif mode == "aggressive":
        return AGGRESSIVE_UNIVERSE
    elif mode == "all":
        return list(ETF_UNIVERSE.keys())
    else:
        return DEFAULT_UNIVERSE


def get_etf_info(ticker):
    """Get ETF metadata"""
    return ETF_UNIVERSE.get(ticker, {})


def get_category(ticker):
    """Get ETF category"""
    return ETF_UNIVERSE.get(ticker, {}).get("category", "unknown")


def filter_by_category(category):
    """Get all ETFs in a category"""
    return [t for t, info in ETF_UNIVERSE.items() if info.get("category") == category]


# ============================================================================
# REPORTING SETTINGS
# ============================================================================

RESULTS_DIR = "results"
GENERATE_PLOTS = True
GENERATE_HTML_REPORT = True
SAVE_TRADES = True

# Console output
VERBOSE = True
SHOW_PROGRESS = True

# Performance metrics to calculate
METRICS = [
    "total_return",
    "cagr",
    "volatility",
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown",
    "calmar_ratio",
    "win_rate",
    "avg_winner",
    "avg_loser",
    "profit_factor",
    "turnover",
    "num_trades",
]

if __name__ == "__main__":
    print("=" * 80)
    print("STOCK MOMENTUM STRATEGY - CONFIGURATION")
    print("=" * 80)

    print(f"\n📊 Asset Universe: {len(ETF_UNIVERSE)} ETFs")
    print(f"   Default: {len(DEFAULT_UNIVERSE)} tickers")
    print(f"   Conservative: {len(CONSERVATIVE_UNIVERSE)} tickers")
    print(f"   Aggressive: {len(AGGRESSIVE_UNIVERSE)} tickers")

    print(f"\n📈 Strategy Parameters:")
    print(f"   BUY threshold: {BUY_THRESHOLD}")
    print(f"   HOLD threshold: {HOLD_THRESHOLD}")
    print(f"   Max position: {MAX_POSITION_SIZE*100:.0f}%")
    print(f"   Min cash: {MIN_CASH_BUFFER*100:.0f}%")

    print(f"\n⚙️  Momentum Settings:")
    print(f"   Short-term: {MOMENTUM_SHORT} days ({MOMENTUM_SHORT_WEIGHT*100:.0f}% weight)")
    print(f"   Long-term: {MOMENTUM_LONG} days ({MOMENTUM_LONG_WEIGHT*100:.0f}% weight)")

    print(f"\n🛡️  Risk Management:")
    print(f"   Max portfolio vol: {MAX_PORTFOLIO_VOLATILITY*100:.0f}%")
    print(f"   SPY regime filter: {SPY_MA_PERIOD}-day MA")
    print(f"   Defensive multiplier: {DEFENSIVE_MULTIPLIER*100:.0f}%")

    print("\n📂 Categories:")
    categories = {}
    for ticker, info in ETF_UNIVERSE.items():
        cat = info.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    for cat, count in sorted(categories.items()):
        print(f"   {cat}: {count} ETFs")

    print("\n" + "=" * 80)
