"""
STOCK MOMENTUM STRATEGY - CORE ENGINE
======================================
Multi-asset momentum with volatility-based position sizing.
Completely automated - no manual selection bias.
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import config

# ============================================================================
# DATA LOADER
# ============================================================================

class DataLoader:
    """Robust data loading with caching"""

    def __init__(self, tickers, start_date, cache_dir='data_cache'):
        self.tickers = tickers
        self.start_date = start_date
        self.cache_dir = cache_dir
        self.prices = None
        self.benchmark = None

    def download_prices(self, verbose=True):
        """Download price data for all tickers"""
        if verbose:
            print(f"\n[*] Downloading {len(self.tickers)} tickers...")
            print(f"   Period: {self.start_date} -> {datetime.now().date()}\n")

        all_prices = {}

        for ticker in self.tickers:
            try:
                data = yf.download(
                    ticker,
                    start=self.start_date,
                    auto_adjust=True,
                    progress=False,
                    threads=False
                )

                if not data.empty and len(data) > 50:
                    # Extract Close price
                    if isinstance(data, pd.DataFrame):
                        if 'Close' in data.columns:
                            close = data['Close']
                        else:
                            continue
                    else:
                        close = data

                    if isinstance(close, pd.DataFrame):
                        close = close.iloc[:, 0]

                    close = close.dropna()
                    close.name = ticker
                    all_prices[ticker] = close

                    if verbose:
                        print(f"  [OK] {ticker:6} - {len(close):4} days")
                else:
                    if verbose:
                        print(f"  [FAIL] {ticker:6} - No data")

            except Exception as e:
                if verbose:
                    print(f"  [FAIL] {ticker:6} - Error: {str(e)[:40]}")

        if not all_prices:
            raise ValueError("No price data downloaded!")

        # Combine into DataFrame
        self.prices = pd.concat(all_prices.values(), axis=1)
        self.prices.columns = list(all_prices.keys())
        self.prices = self.prices.sort_index()

        if verbose:
            print(f"\n[OK] Downloaded {len(self.prices.columns)} tickers")
            print(f"   Date range: {self.prices.index.min().date()} -> {self.prices.index.max().date()}")

        return self.prices

    def download_benchmark(self, benchmark_ticker=None):
        """Download benchmark data"""
        if benchmark_ticker is None:
            benchmark_ticker = config.BENCHMARK

        print(f"\n[*] Downloading benchmark: {benchmark_ticker}")

        data = yf.download(benchmark_ticker, start=self.start_date, auto_adjust=True, progress=False)

        if 'Close' in data.columns:
            self.benchmark = data['Close']
        else:
            self.benchmark = data

        if isinstance(self.benchmark, pd.DataFrame):
            self.benchmark = self.benchmark.iloc[:, 0]

        self.benchmark.name = benchmark_ticker
        print(f"[OK] Benchmark downloaded: {len(self.benchmark)} days\n")

        return self.benchmark


# ============================================================================
# SCORING ENGINE
# ============================================================================

class MomentumScorer:
    """Calculate momentum scores for all assets"""

    def __init__(self, prices):
        self.prices = prices
        self.monthly_prices = prices.resample('ME').last()

    def calculate_momentum(self, period_days):
        """Calculate momentum over specified period (in trading days)"""
        # Convert daily to monthly period
        monthly_period = int(period_days / 21)  # ~21 trading days per month
        return self.monthly_prices.pct_change(monthly_period)

    def calculate_volatility(self, period_days=None):
        """Calculate annualized volatility"""
        if period_days is None:
            period_days = config.VOL_PERIOD

        monthly_period = int(period_days / 21)
        monthly_returns = self.monthly_prices.pct_change()
        vol = monthly_returns.rolling(monthly_period).std() * np.sqrt(12)  # Annualized
        return vol

    def calculate_technical_score(self):
        """Technical indicators: MA crossover + short-term momentum"""
        scores = pd.DataFrame(index=self.monthly_prices.index, columns=self.monthly_prices.columns, dtype=float)

        for ticker in self.monthly_prices.columns:
            prices = self.monthly_prices[ticker]

            # Moving average (50-day equivalent in monthly)
            ma = prices.rolling(int(config.MA_PERIOD / 21)).mean()
            above_ma = (prices > ma).astype(float) * 20  # 20 points if above MA

            # Short-term momentum (3-month)
            mom_3m = prices.pct_change(3)
            positive_mom = (mom_3m > 0).astype(float) * 20  # 20 points if positive

            scores[ticker] = above_ma + positive_mom

        return scores

    def calculate_fundamental_score(self):
        """Fundamental proxy: long-term price momentum (12-month)"""
        scores = pd.DataFrame(index=self.monthly_prices.index, columns=self.monthly_prices.columns, dtype=float)

        for ticker in self.monthly_prices.columns:
            yoy_return = self.monthly_prices[ticker].pct_change(12)

            # Score based on YoY performance
            score = pd.Series(10.0, index=yoy_return.index)
            score[yoy_return > 0.20] = 50.0  # >20% gain = excellent
            score[(yoy_return > 0.10) & (yoy_return <= 0.20)] = 35.0  # 10-20% = good
            score[(yoy_return > 0) & (yoy_return <= 0.10)] = 20.0  # 0-10% = okay

            scores[ticker] = score

        return scores

    def calculate_composite_scores(self):
        """Combine technical + fundamental into composite score (0-100)"""
        technical = self.calculate_technical_score()  # 0-40 range
        fundamental = self.calculate_fundamental_score()  # 10-50 range

        # Composite: 40% technical, 60% fundamental
        composite = technical * 0.4 + fundamental * 0.6

        # Normalize to 0-100
        composite_normalized = (composite / composite.max().max()) * 100

        return composite_normalized

    def get_scores_and_volatility(self):
        """Get latest scores and volatility for all assets"""
        scores = self.calculate_composite_scores()
        volatility = self.calculate_volatility()

        # Get latest values
        latest_scores = scores.iloc[-1]
        latest_vol = volatility.iloc[-1]

        # Combine into DataFrame
        result = pd.DataFrame({
            'score': latest_scores,
            'volatility': latest_vol,
        }).dropna()

        result = result.sort_values('score', ascending=False)

        return result


# ============================================================================
# POSITION SIZER
# ============================================================================

class VolatilityPositionSizer:
    """
    Calculate position sizes based on score and volatility.
    Higher score + lower volatility = larger position.
    """

    def __init__(self, max_position=None, min_position=None, vol_target=None):
        self.max_position = max_position or config.MAX_POSITION_SIZE
        self.min_position = min_position or config.MIN_POSITION_SIZE
        self.vol_target = vol_target or config.VOLATILITY_TARGET

    def calculate_sizes(self, scores_and_vol):
        """
        Calculate position sizes using score/volatility ratio.

        Args:
            scores_and_vol: DataFrame with 'score' and 'volatility' columns

        Returns:
            Series of position weights (sum = 1.0)
        """
        # Filter: only score assets with score > BUY_THRESHOLD
        buy_signals = scores_and_vol[scores_and_vol['score'] >= config.BUY_THRESHOLD].copy()

        if buy_signals.empty:
            return pd.Series(dtype=float)  # No positions

        # Calculate raw weights: score / volatility
        # High score + low vol = high weight
        buy_signals['raw_weight'] = buy_signals['score'] / (buy_signals['volatility'] * 100)

        # Normalize to sum to 1.0
        total_raw = buy_signals['raw_weight'].sum()
        buy_signals['weight'] = buy_signals['raw_weight'] / total_raw

        # Apply min/max constraints
        buy_signals['weight'] = buy_signals['weight'].clip(
            lower=self.min_position,
            upper=self.max_position
        )

        # Re-normalize after clipping
        total_weight = buy_signals['weight'].sum()
        buy_signals['weight'] = buy_signals['weight'] / total_weight

        # Apply cash buffer
        cash_buffer = config.MIN_CASH_BUFFER
        buy_signals['weight'] = buy_signals['weight'] * (1 - cash_buffer)

        return buy_signals['weight']


# ============================================================================
# REGIME FILTER
# ============================================================================

class MarketRegimeFilter:
    """Detect market regime using SPY 200-day MA"""

    def __init__(self, benchmark_prices):
        self.benchmark = benchmark_prices

    def is_defensive_mode(self):
        """Check if market is below 200-day MA"""
        if len(self.benchmark) < config.SPY_MA_PERIOD:
            return False  # Not enough data, assume bullish

        ma_200 = self.benchmark.rolling(config.SPY_MA_PERIOD).mean()
        current_price = self.benchmark.iloc[-1]
        current_ma = ma_200.iloc[-1]

        return current_price < current_ma

    def adjust_positions(self, positions):
        """Reduce positions if in defensive mode"""
        if self.is_defensive_mode():
            print("[WARN] DEFENSIVE MODE: SPY below 200-day MA")
            print(f"   Reducing positions by {(1-config.DEFENSIVE_MULTIPLIER)*100:.0f}%\n")
            return positions * config.DEFENSIVE_MULTIPLIER
        else:
            return positions


# ============================================================================
# PORTFOLIO MANAGER
# ============================================================================

class PortfolioManager:
    """Manage portfolio based on signals"""

    def __init__(self, initial_capital=100000):
        self.capital = initial_capital
        self.positions = {}  # {ticker: shares}
        self.cash = initial_capital
        self.history = []

    def rebalance(self, target_weights, prices, date):
        """
        Rebalance portfolio to target weights.

        Args:
            target_weights: Series of target weights
            prices: Series of current prices
            date: Current date
        """
        portfolio_value = self.calculate_portfolio_value(prices)

        # Calculate target dollar amounts
        target_dollars = target_weights * portfolio_value

        # Calculate trades needed
        trades = []

        for ticker in target_weights.index:
            current_value = self.positions.get(ticker, 0) * prices.get(ticker, 0)
            target_value = target_dollars[ticker]
            trade_value = target_value - current_value

            if abs(trade_value) > 100:  # Only trade if >$100 difference
                trades.append({
                    'date': date,
                    'ticker': ticker,
                    'action': 'BUY' if trade_value > 0 else 'SELL',
                    'value': abs(trade_value),
                    'price': prices[ticker],
                    'shares': int(trade_value / prices[ticker]),
                })

        # Execute trades
        for trade in trades:
            if trade['action'] == 'BUY':
                self.positions[trade['ticker']] = self.positions.get(trade['ticker'], 0) + trade['shares']
                self.cash -= trade['value']
            else:
                self.positions[trade['ticker']] = self.positions.get(trade['ticker'], 0) - trade['shares']
                self.cash += trade['value']

        # Record history
        self.history.append({
            'date': date,
            'portfolio_value': portfolio_value,
            'cash': self.cash,
            'positions': self.positions.copy(),
        })

        return trades

    def calculate_portfolio_value(self, prices):
        """Calculate total portfolio value"""
        position_value = sum(
            shares * prices.get(ticker, 0)
            for ticker, shares in self.positions.items()
        )
        return position_value + self.cash


# ============================================================================
# MAIN STRATEGY CLASS
# ============================================================================

class StockMomentumStrategy:
    """Complete momentum strategy with all components"""

    def __init__(self, universe_tickers, start_date, initial_capital=100000):
        self.tickers = universe_tickers
        self.start_date = start_date
        self.initial_capital = initial_capital

        # Components (initialized in run())
        self.loader = None
        self.scorer = None
        self.sizer = None
        self.regime_filter = None
        self.portfolio = None

    def run(self, verbose=True):
        """Execute complete strategy"""

        if verbose:
            print("\n" + "=" * 80)
            print("STOCK MOMENTUM STRATEGY - EXECUTION")
            print("=" * 80)

        # Step 1: Load data
        if verbose:
            print("\n[STEP 1] Loading data...")
        self.loader = DataLoader(self.tickers, self.start_date)
        prices = self.loader.download_prices(verbose=verbose)
        benchmark = self.loader.download_benchmark()

        # Step 2: Score all assets
        if verbose:
            print("\n[STEP 2] Calculating scores...")
        self.scorer = MomentumScorer(prices)
        scores_and_vol = self.scorer.get_scores_and_volatility()

        if verbose:
            print(f"\n[CHART] Top 10 by score:")
            print(scores_and_vol.head(10))

        # Step 3: Calculate position sizes
        if verbose:
            print("\n[STEP 3] Calculating position sizes...")
        self.sizer = VolatilityPositionSizer()
        target_weights = self.sizer.calculate_sizes(scores_and_vol)

        if verbose:
            print(f"\n[TARGET] Target positions ({len(target_weights)}):")
            for ticker, weight in target_weights.items():
                score = scores_and_vol.loc[ticker, 'score']
                vol = scores_and_vol.loc[ticker, 'volatility']
                print(f"   {ticker:6} {weight:6.1%} (score={score:5.1f}, vol={vol:5.1%})")

        # Step 4: Apply regime filter
        if verbose:
            print("\n[STEP 4] Applying market regime filter...")
        self.regime_filter = MarketRegimeFilter(benchmark)
        adjusted_weights = self.regime_filter.adjust_positions(target_weights)

        # Step 5: Generate report
        if verbose:
            print("\n" + "=" * 80)
            print("STRATEGY EXECUTION COMPLETE")
            print("=" * 80)

        return {
            'target_weights': adjusted_weights,
            'scores': scores_and_vol,
            'prices': prices,
            'benchmark': benchmark,
        }


if __name__ == "__main__":
    # Load universe
    print("Loading trading universe...")
    try:
        universe_df = pd.read_csv('trading_universe.csv')
        tickers = universe_df['ticker'].tolist()[:50]  # Top 50 by liquidity for testing
    except FileNotFoundError:
        print("[FAIL] trading_universe.csv not found!")
        print("   Run universe_builder.py first to build the universe.")
        exit(1)

    # Run strategy
    start_date = (datetime.now() - timedelta(days=365 * config.HISTORY_YEARS)).strftime("%Y-%m-%d")

    strategy = StockMomentumStrategy(
        universe_tickers=tickers,
        start_date=start_date,
        initial_capital=100000
    )

    results = strategy.run(verbose=True)

    print(f"\n[OK] Strategy ready to trade {len(results['target_weights'])} positions")
