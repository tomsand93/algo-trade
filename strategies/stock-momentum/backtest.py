"""
STOCK MOMENTUM STRATEGY - COMPREHENSIVE BACKTEST
=================================================
Full historical backtest with detailed performance metrics and reporting.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import config
from strategy import DataLoader, MomentumScorer, VolatilityPositionSizer, MarketRegimeFilter

# ============================================================================
# BACKTEST ENGINE
# ============================================================================

class Backtester:
    """Execute historical backtest with monthly rebalancing"""

    def __init__(self, universe_tickers, start_date, end_date, initial_capital=100000):
        self.tickers = universe_tickers
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital

        # Results storage
        self.equity_curve = []
        self.positions_history = []
        self.trades = []
        self.monthly_returns = []

    def run(self, verbose=True):
        """Execute full backtest"""

        if verbose:
            print("\n" + "=" * 80)
            print("BACKTEST EXECUTION")
            print("=" * 80)
            print(f"\nPeriod: {self.start_date} -> {self.end_date}")
            print(f"Universe: {len(self.tickers)} tickers")
            print(f"Initial capital: ${self.initial_capital:,.0f}\n")

        # Step 1: Load all data
        if verbose:
            print("[1/5] Loading price data...")
        loader = DataLoader(self.tickers, self.start_date)
        prices = loader.download_prices(verbose=False)
        benchmark = loader.download_benchmark()

        # Filter to backtest period
        prices = prices.loc[self.start_date:self.end_date]
        benchmark = benchmark.loc[self.start_date:self.end_date]

        if verbose:
            print(f"   [OK] Loaded {len(prices.columns)} tickers, {len(prices)} days")

        # Step 2: Resample to monthly
        if verbose:
            print("[2/5] Calculating monthly scores...")
        monthly_prices = prices.resample('ME').last()
        monthly_dates = monthly_prices.index

        if verbose:
            print(f"   [OK] {len(monthly_dates)} monthly rebalances")

        # Step 3: Initialize portfolio
        if verbose:
            print("[3/5] Initializing portfolio...")
        portfolio_value = self.initial_capital
        positions = pd.Series(dtype=float)  # Empty initially
        cash = self.initial_capital

        # Step 4: Monthly rebalancing loop
        if verbose:
            print("[4/5] Running backtest...")
            print()

        scorer = MomentumScorer(prices)
        sizer = VolatilityPositionSizer()
        regime_filter = MarketRegimeFilter(benchmark)

        for i, date in enumerate(monthly_dates):
            if verbose and i % 6 == 0:  # Every 6 months
                print(f"   {date.date()} | Portfolio: ${portfolio_value:,.0f}")

            # Get data up to this point (avoid look-ahead bias)
            historical_prices = prices.loc[:date]

            # Calculate scores
            scorer_current = MomentumScorer(historical_prices)
            scores_and_vol = scorer_current.get_scores_and_volatility()

            # Calculate target weights
            target_weights = sizer.calculate_sizes(scores_and_vol)

            # Apply regime filter
            current_benchmark = benchmark.loc[:date]
            regime_filter_current = MarketRegimeFilter(current_benchmark)
            adjusted_weights = regime_filter_current.adjust_positions(target_weights)

            # Get current prices
            current_prices = monthly_prices.loc[date]

            # Update portfolio value first (mark-to-market existing positions)
            current_position_value = (positions * current_prices).sum()
            portfolio_value = current_position_value + cash

            # Calculate available capital (keep cash buffer as percentage)
            cash_buffer_pct = config.MIN_CASH_BUFFER
            available_capital = portfolio_value * (1 - cash_buffer_pct)

            # Rebalance portfolio (using available capital, not full portfolio value)
            new_positions, trades_made = self._rebalance(
                positions, adjusted_weights, current_prices, available_capital, date
            )

            positions = new_positions
            self.trades.extend(trades_made)

            # Update cash and portfolio value after rebalancing
            position_value = (positions * current_prices).sum()
            cash = portfolio_value - position_value  # Remaining cash after investing
            portfolio_value = position_value + cash

            # Record equity curve
            self.equity_curve.append({
                'date': date,
                'portfolio_value': portfolio_value,
                'positions_value': position_value,
                'cash': cash,
                'num_positions': len(positions[positions > 0]),
            })

            # Record positions
            self.positions_history.append({
                'date': date,
                'positions': positions.copy(),
                'weights': adjusted_weights.copy(),
            })

        # Step 5: Calculate returns
        if verbose:
            print(f"\n[5/5] Calculating performance metrics...")

        equity_df = pd.DataFrame(self.equity_curve).set_index('date')
        self.monthly_returns = equity_df['portfolio_value'].pct_change().dropna()

        # Benchmark returns
        benchmark_monthly = benchmark.resample('ME').last()
        benchmark_returns = benchmark_monthly.pct_change().dropna()

        if verbose:
            print("   [OK] Backtest complete\n")
            print("=" * 80)

        return {
            'equity_curve': equity_df,
            'returns': self.monthly_returns,
            'benchmark_returns': benchmark_returns,
            'trades': pd.DataFrame(self.trades),
            'positions_history': self.positions_history,
            'final_value': portfolio_value,
        }

    def _rebalance(self, current_positions, target_weights, prices, portfolio_value, date):
        """Execute rebalancing trades"""

        # Calculate target shares
        target_dollars = target_weights * portfolio_value
        target_shares = (target_dollars / prices).fillna(0).astype(int)

        # Calculate trades needed
        trades = []
        new_positions = current_positions.copy()

        for ticker in target_shares.index.union(current_positions.index):
            current_shares = current_positions.get(ticker, 0)
            target_share_count = target_shares.get(ticker, 0)
            share_diff = target_share_count - current_shares

            if abs(share_diff) > 0:
                price = prices.get(ticker, np.nan)

                if pd.notna(price):
                    trades.append({
                        'date': date,
                        'ticker': ticker,
                        'action': 'BUY' if share_diff > 0 else 'SELL',
                        'shares': abs(share_diff),
                        'price': price,
                        'value': abs(share_diff * price),
                    })

                    new_positions[ticker] = target_share_count

        # Remove zero positions
        new_positions = new_positions[new_positions > 0]

        return new_positions, trades


# ============================================================================
# PERFORMANCE METRICS
# ============================================================================

class PerformanceAnalyzer:
    """Calculate comprehensive performance metrics"""

    def __init__(self, returns, benchmark_returns, equity_curve, trades):
        self.returns = returns
        self.benchmark_returns = benchmark_returns
        self.equity_curve = equity_curve
        self.trades = trades

    def calculate_all_metrics(self):
        """Calculate all performance metrics"""

        metrics = {}

        # === Basic Returns ===
        total_return = (self.equity_curve['portfolio_value'].iloc[-1] /
                       self.equity_curve['portfolio_value'].iloc[0]) - 1
        metrics['total_return'] = total_return

        # CAGR
        years = len(self.returns) / 12
        metrics['cagr'] = (1 + total_return) ** (1 / years) - 1

        # === Risk Metrics ===
        metrics['volatility'] = self.returns.std() * np.sqrt(12)  # Annualized

        # Sharpe Ratio (assuming 0% risk-free rate)
        metrics['sharpe_ratio'] = metrics['cagr'] / metrics['volatility'] if metrics['volatility'] > 0 else 0

        # Sortino Ratio (downside deviation)
        downside_returns = self.returns[self.returns < 0]
        downside_std = downside_returns.std() * np.sqrt(12)
        metrics['sortino_ratio'] = metrics['cagr'] / downside_std if downside_std > 0 else 0

        # Maximum Drawdown
        cumulative = (1 + self.returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        metrics['max_drawdown'] = drawdown.min()

        # Calmar Ratio
        metrics['calmar_ratio'] = metrics['cagr'] / abs(metrics['max_drawdown']) if metrics['max_drawdown'] != 0 else 0

        # === Trade Statistics ===
        if not self.trades.empty:
            # Group trades by ticker to get round-trips
            metrics['num_trades'] = len(self.trades)

            # Win rate (approximate - based on monthly returns)
            win_months = len(self.returns[self.returns > 0])
            total_months = len(self.returns)
            metrics['win_rate'] = win_months / total_months if total_months > 0 else 0

            # Average winner/loser
            winners = self.returns[self.returns > 0]
            losers = self.returns[self.returns < 0]
            metrics['avg_winner'] = winners.mean() if len(winners) > 0 else 0
            metrics['avg_loser'] = losers.mean() if len(losers) > 0 else 0

            # Profit factor
            total_gains = winners.sum()
            total_losses = abs(losers.sum())
            metrics['profit_factor'] = total_gains / total_losses if total_losses > 0 else np.inf

            # Turnover (approximate)
            total_traded = self.trades['value'].sum()
            avg_portfolio_value = self.equity_curve['portfolio_value'].mean()
            metrics['turnover'] = total_traded / (avg_portfolio_value * years)
        else:
            metrics['num_trades'] = 0
            metrics['win_rate'] = 0
            metrics['avg_winner'] = 0
            metrics['avg_loser'] = 0
            metrics['profit_factor'] = 0
            metrics['turnover'] = 0

        # === Benchmark Comparison ===
        # Align benchmark returns with strategy returns
        aligned_benchmark = self.benchmark_returns.reindex(self.returns.index)
        aligned_benchmark = aligned_benchmark.dropna()
        aligned_strategy = self.returns.reindex(aligned_benchmark.index)

        bench_total = (1 + aligned_benchmark).cumprod().iloc[-1] - 1
        metrics['benchmark_return'] = bench_total
        metrics['benchmark_cagr'] = (1 + bench_total) ** (1 / years) - 1
        metrics['benchmark_volatility'] = aligned_benchmark.std() * np.sqrt(12)

        metrics['alpha'] = metrics['cagr'] - metrics['benchmark_cagr']

        # Beta
        covariance = np.cov(aligned_strategy, aligned_benchmark)[0, 1]
        benchmark_variance = np.var(aligned_benchmark)
        metrics['beta'] = covariance / benchmark_variance if benchmark_variance > 0 else 0

        # Information Ratio
        excess_returns = aligned_strategy - aligned_benchmark
        tracking_error = excess_returns.std() * np.sqrt(12)
        metrics['information_ratio'] = metrics['alpha'] / tracking_error if tracking_error > 0 else 0

        return metrics

    def print_summary(self, metrics):
        """Print formatted performance summary"""

        print("\n" + "=" * 80)
        print("PERFORMANCE SUMMARY")
        print("=" * 80)

        print("\n[RETURNS]")
        print(f"   Total Return:        {metrics['total_return']:>10.2%}")
        print(f"   CAGR:                {metrics['cagr']:>10.2%}")

        print("\n[RISK METRICS]")
        print(f"   Volatility:          {metrics['volatility']:>10.2%}")
        print(f"   Max Drawdown:        {metrics['max_drawdown']:>10.2%}")
        print(f"   Sharpe Ratio:        {metrics['sharpe_ratio']:>10.2f}")
        print(f"   Sortino Ratio:       {metrics['sortino_ratio']:>10.2f}")
        print(f"   Calmar Ratio:        {metrics['calmar_ratio']:>10.2f}")

        print("\n[TRADING STATISTICS]")
        print(f"   Total Trades:        {metrics['num_trades']:>10,.0f}")
        print(f"   Win Rate:            {metrics['win_rate']:>10.2%}")
        print(f"   Avg Winner:          {metrics['avg_winner']:>10.2%}")
        print(f"   Avg Loser:           {metrics['avg_loser']:>10.2%}")
        print(f"   Profit Factor:       {metrics['profit_factor']:>10.2f}")
        print(f"   Annual Turnover:     {metrics['turnover']:>10.2f}x")

        print("\n[vs BENCHMARK]")
        print(f"   Benchmark CAGR:      {metrics['benchmark_cagr']:>10.2%}")
        print(f"   Benchmark Vol:       {metrics['benchmark_volatility']:>10.2%}")
        print(f"   Alpha:               {metrics['alpha']:>10.2%}")
        print(f"   Beta:                {metrics['beta']:>10.2f}")
        print(f"   Information Ratio:   {metrics['information_ratio']:>10.2f}")

        print("\n" + "=" * 80)

    def plot_results(self, save_path='results/backtest_results.png'):
        """Generate performance plots"""

        fig, axes = plt.subplots(3, 1, figsize=(14, 10))

        # Plot 1: Equity Curve
        ax1 = axes[0]
        equity = self.equity_curve['portfolio_value']
        equity_norm = equity / equity.iloc[0] * 100

        bench_monthly = self.benchmark_returns.reindex(equity.index)
        bench_cumulative = (1 + bench_monthly.fillna(0)).cumprod() * 100

        ax1.plot(equity.index, equity_norm, label='Strategy', linewidth=2)
        ax1.plot(equity.index, bench_cumulative, label='Benchmark (SPY)', linewidth=2, alpha=0.7)
        ax1.set_title('Equity Curve (Normalized to 100)', fontsize=14, fontweight='bold')
        ax1.set_ylabel('Value')
        ax1.legend()
        ax1.grid(alpha=0.3)

        # Plot 2: Drawdown
        ax2 = axes[1]
        cumulative = (1 + self.returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max

        ax2.fill_between(drawdown.index, drawdown * 100, 0, color='red', alpha=0.3)
        ax2.plot(drawdown.index, drawdown * 100, color='red', linewidth=1)
        ax2.set_title('Drawdown', fontsize=14, fontweight='bold')
        ax2.set_ylabel('Drawdown (%)')
        ax2.grid(alpha=0.3)

        # Plot 3: Rolling 12-Month Returns
        ax3 = axes[2]
        rolling_returns = self.returns.rolling(12).apply(lambda x: (1 + x).prod() - 1, raw=False)

        ax3.plot(rolling_returns.index, rolling_returns * 100, linewidth=2)
        ax3.axhline(0, color='black', linewidth=0.8, linestyle='--')
        ax3.set_title('Rolling 12-Month Returns', fontsize=14, fontweight='bold')
        ax3.set_ylabel('Return (%)')
        ax3.set_xlabel('Date')
        ax3.grid(alpha=0.3)

        plt.tight_layout()
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"\n[CHART] Chart saved: {save_path}")

        return fig


# ============================================================================
# MAIN - RUN BACKTEST
# ============================================================================

if __name__ == "__main__":
    import os
    os.chdir(r"C:\Users\Tom1\Desktop\TRADING\production\stock_momentum")

    # Create results directory
    os.makedirs('results', exist_ok=True)

    # Load universe
    print("Loading trading universe...")
    try:
        universe_df = pd.read_csv('trading_universe.csv')
        # Use top N by liquidity for faster backtest
        tickers = universe_df.head(50)['ticker'].tolist()
        print(f"[OK] Using {len(tickers)} tickers for backtest\n")
    except FileNotFoundError:
        print("[FAIL] trading_universe.csv not found!")
        print("   Run: python universe_builder.py")
        exit(1)

    # Set backtest period
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * config.BACKTEST_YEARS)

    # Run backtest
    backtester = Backtester(
        universe_tickers=tickers,
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        initial_capital=100000
    )

    results = backtester.run(verbose=True)

    # Analyze performance
    analyzer = PerformanceAnalyzer(
        returns=results['returns'],
        benchmark_returns=results['benchmark_returns'],
        equity_curve=results['equity_curve'],
        trades=results['trades'],
    )

    metrics = analyzer.calculate_all_metrics()
    analyzer.print_summary(metrics)

    # Generate plots
    analyzer.plot_results('results/backtest_results.png')

    # Save results
    results['equity_curve'].to_csv('results/equity_curve.csv')
    results['trades'].to_csv('results/trades.csv', index=False)

    print("\n[SAVE] Results saved to results/ directory")
    print("\n[OK] Backtest complete!")
