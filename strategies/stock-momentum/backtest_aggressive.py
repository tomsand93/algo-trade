"""
AGGRESSIVE MOMENTUM STRATEGY - BACKTEST
========================================
- Predict strong stocks each month using momentum
- ONLY sell winners (take profits)
- HOLD losers until recovery
- No defensive mode
- Test on 8-year window
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import config
from strategy import DataLoader, MomentumScorer, VolatilityPositionSizer
from backtest import PerformanceAnalyzer

# ============================================================================
# AGGRESSIVE BACKTEST ENGINE
# ============================================================================

class AggressiveBacktester:
    """Backtest with 'sell winners only' logic"""

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

        # Track cost basis for each position
        self.cost_basis = {}  # ticker -> average purchase price

    def run(self, verbose=True):
        """Execute full backtest"""

        if verbose:
            print("\n" + "=" * 80)
            print("AGGRESSIVE BACKTEST EXECUTION")
            print("=" * 80)
            print(f"\nPeriod: {self.start_date} -> {self.end_date}")
            print(f"Universe: {len(self.tickers)} tickers")
            print(f"Initial capital: ${self.initial_capital:,.0f}")
            print(f"\nStrategy: ONLY sell winners, HOLD losers")
            print(f"Defensive mode: DISABLED\n")

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
        positions = pd.Series(dtype=float)  # Empty initially (shares held)
        cash = self.initial_capital

        # Step 4: Monthly rebalancing loop
        if verbose:
            print("[4/5] Running backtest...")
            print()

        scorer = MomentumScorer(prices)
        sizer = VolatilityPositionSizer()

        for i, date in enumerate(monthly_dates):
            if verbose and i % 12 == 0:  # Every 12 months
                print(f"   {date.date()} | Portfolio: ${portfolio_value:,.0f} | Cash: ${cash:,.0f}")

            # Get data up to this point (avoid look-ahead bias)
            historical_prices = prices.loc[:date]

            # Calculate scores
            scorer_current = MomentumScorer(historical_prices)
            scores_and_vol = scorer_current.get_scores_and_volatility()

            # Calculate target weights (top momentum stocks)
            target_weights = sizer.calculate_sizes(scores_and_vol)

            # NO DEFENSIVE MODE - stay fully invested

            # Get current prices
            current_prices = monthly_prices.loc[date]

            # Update portfolio value first (mark-to-market existing positions)
            current_position_value = (positions * current_prices).sum()
            portfolio_value = current_position_value + cash

            # Calculate available capital (keep cash buffer as percentage)
            cash_buffer_pct = config.MIN_CASH_BUFFER
            available_capital = portfolio_value * (1 - cash_buffer_pct)

            # AGGRESSIVE REBALANCE: Only sell winners, hold losers
            new_positions, trades_made = self._aggressive_rebalance(
                positions, target_weights, current_prices, available_capital, date
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

        if verbose:
            print(f"\n   Final Portfolio: ${portfolio_value:,.0f}")
            print(f"\n[5/5] Calculating performance metrics...")

        equity_df = pd.DataFrame(self.equity_curve).set_index('date')
        self.monthly_returns = equity_df['portfolio_value'].pct_change().dropna()

        # Benchmark returns
        benchmark_monthly = benchmark.resample('ME').last()
        benchmark_returns = benchmark_monthly.pct_change().dropna()
        benchmark_returns = benchmark_returns.reindex(self.monthly_returns.index).dropna()

        if verbose:
            print("   [OK] Backtest complete\n")
            print("=" * 80 + "\n")

        return {
            'equity_curve': equity_df,
            'returns': self.monthly_returns,
            'benchmark_returns': benchmark_returns,
            'trades': pd.DataFrame(self.trades),
            'positions_history': self.positions_history,
            'final_value': portfolio_value,
        }

    def _aggressive_rebalance(self, current_positions, target_weights, prices, portfolio_value, date):
        """
        AGGRESSIVE REBALANCING LOGIC:
        1. Predict top momentum stocks (target_weights)
        2. For existing positions:
           - If in profit AND not in target list -> SELL (take profit)
           - If in loss -> HOLD (never sell at loss)
        3. Use freed capital + available cash to buy top predictions
        """

        # Calculate target shares
        target_dollars = target_weights * portfolio_value
        target_shares = (target_dollars / prices).fillna(0).astype(int)

        # Calculate trades needed
        trades = []
        new_positions = current_positions.copy()

        # Process each position
        for ticker in current_positions.index:
            if current_positions[ticker] <= 0:
                continue

            current_shares = current_positions[ticker]
            current_price = prices.get(ticker, np.nan)

            if pd.isna(current_price):
                continue

            # Get cost basis (average purchase price)
            cost_basis = self.cost_basis.get(ticker, current_price)

            # Calculate profit/loss
            pnl_pct = (current_price - cost_basis) / cost_basis

            # Decision logic:
            target_share_count = target_shares.get(ticker, 0)

            if ticker not in target_weights.index or target_share_count == 0:
                # Stock no longer in prediction list
                if pnl_pct > 0:
                    # IN PROFIT -> SELL (take profit)
                    trades.append({
                        'date': date,
                        'ticker': ticker,
                        'action': 'SELL',
                        'shares': current_shares,
                        'price': current_price,
                        'value': current_shares * current_price,
                        'pnl_pct': pnl_pct,
                        'reason': 'TAKE_PROFIT'
                    })
                    new_positions[ticker] = 0
                    if ticker in self.cost_basis:
                        del self.cost_basis[ticker]
                else:
                    # IN LOSS -> HOLD (never sell at loss)
                    trades.append({
                        'date': date,
                        'ticker': ticker,
                        'action': 'HOLD',
                        'shares': current_shares,
                        'price': current_price,
                        'value': current_shares * current_price,
                        'pnl_pct': pnl_pct,
                        'reason': 'HOLD_LOSER'
                    })
                    # Keep position unchanged
            else:
                # Stock still in prediction list
                share_diff = target_share_count - current_shares

                if share_diff > 0:
                    # BUY MORE
                    trades.append({
                        'date': date,
                        'ticker': ticker,
                        'action': 'BUY_MORE',
                        'shares': share_diff,
                        'price': current_price,
                        'value': share_diff * current_price,
                        'pnl_pct': pnl_pct,
                        'reason': 'ADD_TO_WINNER' if pnl_pct > 0 else 'AVG_DOWN_LOSER'
                    })
                    # Update cost basis (weighted average)
                    old_value = current_shares * cost_basis
                    new_value = share_diff * current_price
                    total_shares = current_shares + share_diff
                    self.cost_basis[ticker] = (old_value + new_value) / total_shares
                    new_positions[ticker] = total_shares

                elif share_diff < 0:
                    # Reduce position
                    if pnl_pct > 0:
                        # TRIM WINNER
                        trades.append({
                            'date': date,
                            'ticker': ticker,
                            'action': 'TRIM',
                            'shares': abs(share_diff),
                            'price': current_price,
                            'value': abs(share_diff) * current_price,
                            'pnl_pct': pnl_pct,
                            'reason': 'TRIM_WINNER'
                        })
                        new_positions[ticker] = target_share_count
                        # Keep cost basis same
                    else:
                        # In loss, keep full position (don't trim losers)
                        trades.append({
                            'date': date,
                            'ticker': ticker,
                            'action': 'HOLD',
                            'shares': current_shares,
                            'price': current_price,
                            'value': current_shares * current_price,
                            'pnl_pct': pnl_pct,
                            'reason': 'HOLD_LOSER_NO_TRIM'
                        })

        # Buy new positions that aren't currently held
        for ticker in target_shares.index:
            if ticker not in current_positions.index or current_positions.get(ticker, 0) == 0:
                target_share_count = target_shares[ticker]
                if target_share_count > 0:
                    price = prices.get(ticker, np.nan)
                    if pd.notna(price):
                        trades.append({
                            'date': date,
                            'ticker': ticker,
                            'action': 'BUY_NEW',
                            'shares': target_share_count,
                            'price': price,
                            'value': target_share_count * price,
                            'pnl_pct': 0.0,
                            'reason': 'NEW_POSITION'
                        })
                        new_positions[ticker] = target_share_count
                        self.cost_basis[ticker] = price

        # Remove zero positions
        new_positions = new_positions[new_positions > 0]

        return new_positions, trades


# ============================================================================
# RUN 8-YEAR BACKTEST
# ============================================================================

if __name__ == '__main__':
    print("\n" + "="*80)
    print("AGGRESSIVE MOMENTUM STRATEGY - 8-YEAR BACKTEST")
    print("="*80)
    print("\nStrategy Rules:")
    print("  1. Predict top momentum stocks each month")
    print("  2. ONLY sell winners (take profits)")
    print("  3. HOLD all losing positions (wait for recovery)")
    print("  4. NO defensive mode (stay fully invested)")
    print("  5. Rebalance monthly\n")

    # 8-year backtest (2016-2023)
    backtester = AggressiveBacktester(
        universe_tickers=config.DEFAULT_UNIVERSE,
        start_date='2016-01-01',
        end_date='2023-12-31',
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

    # Print results
    print("\n" + "="*80)
    print("PERFORMANCE METRICS (8-YEAR BACKTEST: 2016-2023)")
    print("="*80)
    print(f"\n{'Metric':<25} {'Strategy':>15} {'Benchmark':>15}")
    print("-" * 80)
    print(f"{'Total Return':<25} {metrics['total_return']:>14.2%} {metrics.get('benchmark_total_return', 0):>14.2%}")
    print(f"{'CAGR':<25} {metrics['cagr']:>14.2%} {metrics.get('benchmark_cagr', 0):>14.2%}")
    print(f"{'Volatility':<25} {metrics['volatility']:>14.2%} {metrics.get('benchmark_volatility', 0):>14.2%}")
    print(f"{'Sharpe Ratio':<25} {metrics['sharpe_ratio']:>14.2f} {metrics.get('benchmark_sharpe', 0):>14.2f}")
    print(f"{'Sortino Ratio':<25} {metrics['sortino_ratio']:>14.2f}")
    print(f"{'Max Drawdown':<25} {metrics['max_drawdown']:>14.2%} {metrics.get('benchmark_max_dd', 0):>14.2%}")
    print(f"{'Win Rate':<25} {metrics.get('win_rate', 0):>14.2%}")
    print(f"{'Total Trades':<25} {metrics.get('num_trades', 0):>15.0f}")
    print("="*80)

    # Analyze trade types
    if not results['trades'].empty:
        trades_df = results['trades']
        print(f"\nTrade Analysis:")
        print(f"  Total trades: {len(trades_df)}")
        if 'reason' in trades_df.columns:
            print(f"\n  By Action:")
            for reason in trades_df['reason'].value_counts().head(10).items():
                print(f"    {reason[0]:<20}: {reason[1]:>5} trades")

            # Profit analysis
            if 'pnl_pct' in trades_df.columns:
                profit_trades = trades_df[trades_df['pnl_pct'] > 0]
                loss_trades = trades_df[trades_df['pnl_pct'] < 0]
                print(f"\n  Profit/Loss at Trade Time:")
                print(f"    Profitable positions: {len(profit_trades)} ({len(profit_trades)/len(trades_df)*100:.1f}%)")
                print(f"    Losing positions held: {len(loss_trades)} ({len(loss_trades)/len(trades_df)*100:.1f}%)")
