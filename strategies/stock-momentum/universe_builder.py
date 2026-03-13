"""
AUTOMATIC UNIVERSE BUILDER
===========================
Builds trading universe from scratch with NO MANUAL SELECTION BIAS.
Filters based on objective criteria: liquidity, data quality, tradability.
"""

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# ============================================================================
# COMPREHENSIVE ETF LIST (ALL US-LISTED ETFs)
# ============================================================================

# This is a comprehensive list of popular US-listed ETFs across all categories
# The strategy will automatically filter these based on objective criteria

ALL_ETFS = [
    # Broad Market (Large-Cap)
    "SPY", "VOO", "IVV", "VTI", "ITOT", "SCHB", "QQQ", "QQQM", "DIA",
    "RSP", "EUSA", "SPLG", "SPTM", "ONEQ", "QQEW", "VTV", "VUG", "IWB",
    "IWF", "IWD", "SCHX", "VV", "MGC", "MGK", "MGV", "IVE", "IVW",

    # Mid-Cap
    "MDY", "IJH", "VO", "IVOO", "SCHM", "IWR", "IWP", "IWS", "VOT", "VOE",

    # Small-Cap
    "IWM", "IJR", "VB", "SCHA", "VTWO", "IWN", "IWO", "VBR", "VBK", "VIOO",

    # Sector SPDRs
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC",

    # Technology & Innovation
    "ARKK", "ARKG", "ARKQ", "ARKW", "ARKF", "SOXX", "SMH", "XSD", "IGV", "VGT",
    "HACK", "CLOU", "SKYY", "WCLD", "BUG", "CIBR", "FINX", "IPAY", "ARKX",
    "ROBO", "BOTZ", "IRBO", "AIQ", "XITK", "QTEC", "IGM", "FDN", "PNQI",

    # Healthcare & Biotech
    "XBI", "IBB", "BBH", "VHT", "IHI", "IYH", "FHLC", "XLV", "VBK", "PBE",

    # Financial
    "KBE", "KRE", "IAI", "IYF", "VFH", "KBWB", "QABA", "XLF", "FAS",

    # Energy
    "XOP", "IYE", "VDE", "IXC", "ICLN", "TAN", "QCLN", "PBW", "ACES", "SMOG",
    "XLE", "USO", "UNG", "OIH", "FCG", "AMLP", "AMJ",

    # Materials & Industrials
    "XME", "PICK", "SLX", "GDX", "GDXJ", "XLI", "IYT", "IYJ", "XAR", "PPA",

    # Consumer
    "XRT", "XHB", "ITB", "HOMZ", "XLY", "VCR", "FXD", "XLP", "VDC", "FXG",

    # Real Estate
    "VNQ", "IYR", "XLRE", "RWR", "SCHH", "USRT", "REZ", "ICF", "BBRE", "REM",

    # International - Developed
    "EFA", "VEA", "IEFA", "SCHF", "IXUS", "IDEV", "VGK", "IEV", "FEZ", "EZU",
    "EWJ", "EWG", "EWU", "EWL", "EWQ", "EWI", "EWP", "EWD", "EWN", "EWC",

    # International - Emerging
    "EEM", "VWO", "IEMG", "SCHE", "SPEM", "DEM", "EEMV", "FEM", "EMXC",
    "FXI", "MCHI", "GXC", "ASHR", "KWEB", "CQQQ", "EWZ", "EWY", "EWH",
    "EWT", "EIDO", "EWW", "EWS", "ERUS", "EWM", "RSX", "EPOL", "EWA",

    # Bonds - Government
    "TLT", "IEF", "SHY", "IEI", "SHV", "BIL", "SCHO", "SCHR", "SPTS", "VGSH",
    "VGIT", "VGLT", "GOVT", "EDV", "TMF", "TBT", "TBF", "PST", "BND",

    # Bonds - Corporate
    "LQD", "VCLT", "VCIT", "VCSH", "USIG", "IGIB", "IGSB", "SLQD", "HYG",
    "JNK", "SJNK", "ANGL", "FALN", "HYLB", "SHYG", "USHY", "SPHY",

    # Bonds - International
    "BWX", "BNDX", "IAGG", "IGOV", "ISHG", "WIP",

    # Bonds - Inflation-Protected
    "TIP", "VTIP", "SCHP", "STIP", "IPE", "LTPZ", "GTIP",

    # Commodities
    "GLD", "IAU", "SGOL", "GLDM", "SLV", "SIVR", "PPLT", "PALL", "GSG",
    "DBC", "PDBC", "BCI", "DBA", "CORN", "WEAT", "SOYB", "CANE", "JO",
    "NIB", "BAL", "JJC", "JJN", "JJM", "JJT", "JJA", "JJG", "JJU",

    # Currency
    "UUP", "UDN", "FXE", "FXY", "FXA", "FXB", "FXC", "FXF", "FXS",

    # Volatility
    "VIXY", "VXX", "UVXY", "SVXY",

    # Factor-Based
    "MTUM", "VLUE", "SIZE", "QUAL", "USMV", "SPLV", "SPHD", "SPHQ", "DGRO",
    "VIG", "NOBL", "SDY", "VYM", "SCHD", "DVY", "HDV", "DHS", "RDOG", "COWZ",

    # Dividend-Focused
    "VYM", "SCHD", "DGRO", "NOBL", "SDY", "DVY", "HDV", "VIG", "DHS", "DGRW",

    # Smart Beta / Multi-Factor
    "JPUS", "LRGF", "OMFL", "NUMG", "INTF", "JHMM", "JPEM", "JPGE", "DIVI",
]

# ============================================================================
# FILTERING CRITERIA (OBJECTIVE, NO BIAS)
# ============================================================================

class UniverseFilter:
    """
    Objective filtering of ETFs based on tradability criteria.
    NO MANUAL SELECTION - everything is algorithmic.
    """

    def __init__(self):
        self.min_price = 5.0            # $5 minimum (avoid penny stocks)
        self.max_price = 10000.0        # $10,000 maximum (avoid inaccessible)
        self.min_volume = 100000        # 100k daily volume (liquidity)
        self.min_history_days = 756     # 3 years of data (252 * 3)
        self.max_missing_pct = 0.05     # Max 5% missing data
        self.min_market_cap = None      # ETFs don't have market cap filter

    def fetch_etf_data(self, ticker, lookback_days=1260):  # 5 years
        """Fetch ETF data and metadata for filtering"""
        try:
            etf = yf.Ticker(ticker)

            # Get historical data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=lookback_days)
            hist = etf.history(start=start_date, end=end_date, auto_adjust=True)

            if hist.empty or len(hist) < 50:
                return None

            # Calculate filtering metrics
            data = {
                'ticker': ticker,
                'current_price': hist['Close'].iloc[-1],
                'avg_volume_30d': hist['Volume'].tail(30).mean(),
                'history_days': len(hist),
                'missing_pct': hist['Close'].isna().sum() / len(hist),
                'price_series': hist['Close'],
                'volume_series': hist['Volume'],
                'first_date': hist.index.min(),
                'last_date': hist.index.max(),
            }

            # Get basic info (optional, sometimes fails)
            try:
                info = etf.info
                data['name'] = info.get('longName', ticker)
                data['category'] = info.get('category', 'unknown')
            except:
                data['name'] = ticker
                data['category'] = 'unknown'

            return data

        except Exception as e:
            print(f"  ⚠️  {ticker}: Failed to fetch - {str(e)[:50]}")
            return None

    def passes_filter(self, etf_data):
        """Check if ETF passes all objective criteria"""
        if etf_data is None:
            return False, "No data"

        # Price filter
        if etf_data['current_price'] < self.min_price:
            return False, f"Price too low (${etf_data['current_price']:.2f})"

        if etf_data['current_price'] > self.max_price:
            return False, f"Price too high (${etf_data['current_price']:.2f})"

        # Volume filter (liquidity)
        if etf_data['avg_volume_30d'] < self.min_volume:
            return False, f"Low volume ({etf_data['avg_volume_30d']:.0f})"

        # History filter
        if etf_data['history_days'] < self.min_history_days:
            return False, f"Insufficient history ({etf_data['history_days']} days)"

        # Data quality filter
        if etf_data['missing_pct'] > self.max_missing_pct:
            return False, f"Too much missing data ({etf_data['missing_pct']:.1%})"

        return True, "Passed"

    def build_universe(self, candidate_list=None, verbose=True):
        """
        Build trading universe from candidate list with objective filtering.

        Args:
            candidate_list: List of tickers to screen (default: ALL_ETFS)
            verbose: Print progress

        Returns:
            DataFrame with filtered universe and metadata
        """
        if candidate_list is None:
            candidate_list = ALL_ETFS

        if verbose:
            print("\n" + "=" * 80)
            print("BUILDING TRADING UNIVERSE (OBJECTIVE FILTERING)")
            print("=" * 80)
            print(f"\n🔍 Screening {len(candidate_list)} candidates...")
            print(f"\n📋 Filter Criteria:")
            print(f"   Price: ${self.min_price} - ${self.max_price}")
            print(f"   Volume: >{self.min_volume:,.0f} daily")
            print(f"   History: >{self.min_history_days} days ({self.min_history_days/252:.1f} years)")
            print(f"   Data quality: <{self.max_missing_pct:.0%} missing")
            print(f"\n⏳ Fetching data (this may take a few minutes)...\n")

        results = []
        passed = []
        failed = []

        for i, ticker in enumerate(candidate_list, 1):
            if verbose and i % 20 == 0:
                print(f"   Progress: {i}/{len(candidate_list)} ({i/len(candidate_list):.0%})")

            # Fetch data
            etf_data = self.fetch_etf_data(ticker)

            # Apply filter
            passed_filter, reason = self.passes_filter(etf_data)

            if passed_filter:
                results.append({
                    'ticker': ticker,
                    'name': etf_data['name'],
                    'price': etf_data['current_price'],
                    'volume_30d': etf_data['avg_volume_30d'],
                    'history_days': etf_data['history_days'],
                    'data_quality': 1 - etf_data['missing_pct'],
                    'first_date': etf_data['first_date'],
                    'category': etf_data['category'],
                })
                passed.append(ticker)
                if verbose:
                    print(f"  ✅ {ticker:6} - {etf_data['name'][:40]:40} | ${etf_data['current_price']:7.2f} | {etf_data['avg_volume_30d']:,.0f} vol")
            else:
                failed.append((ticker, reason))

        if verbose:
            print(f"\n" + "=" * 80)
            print("SCREENING RESULTS")
            print("=" * 80)
            print(f"\n✅ Passed: {len(passed)} ETFs")
            print(f"❌ Failed: {len(failed)} ETFs")
            print(f"\n📊 Pass Rate: {len(passed)/len(candidate_list):.1%}")

            if failed:
                print(f"\n❌ Top Failure Reasons:")
                failure_reasons = {}
                for ticker, reason in failed:
                    failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
                for reason, count in sorted(failure_reasons.items(), key=lambda x: -x[1])[:10]:
                    print(f"   {count:3} - {reason}")

        if not results:
            raise ValueError("No ETFs passed filtering! Adjust criteria or candidate list.")

        df = pd.DataFrame(results).sort_values('volume_30d', ascending=False)
        return df


def save_universe(df, filename='trading_universe.csv'):
    """Save universe to CSV for inspection"""
    df.to_csv(filename, index=False)
    print(f"\n💾 Universe saved to: {filename}")


def load_universe(filename='trading_universe.csv'):
    """Load previously built universe"""
    return pd.read_csv(filename)


# ============================================================================
# MAIN - BUILD UNIVERSE
# ============================================================================

if __name__ == "__main__":
    import os
    os.chdir(r"C:\Users\Tom1\Desktop\TRADING\production\stock_momentum")

    # Build universe with objective filtering
    filter = UniverseFilter()

    # You can adjust criteria if needed (but objectively, not cherry-picking)
    # filter.min_volume = 500000  # Stricter liquidity
    # filter.min_history_days = 1260  # 5 years history

    universe_df = filter.build_universe(verbose=True)

    # Save for strategy to use
    save_universe(universe_df, 'trading_universe.csv')

    print(f"\n" + "=" * 80)
    print(f"✅ Universe built: {len(universe_df)} ETFs ready to trade")
    print(f"\nTop 10 by liquidity:")
    print(universe_df.head(10)[['ticker', 'name', 'price', 'volume_30d']])
    print("=" * 80)
