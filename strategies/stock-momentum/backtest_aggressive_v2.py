"""
AGGRESSIVE MOMENTUM STRATEGY V2 - BACKTEST
==========================================
IMPROVED LOGIC:
- Predict strong stocks each month using momentum
- ONLY sell if: (1) In profit AND (2) Predict stock will decline
- HOLD all losers until recovery
- HOLD winners if still strong
- No defensive mode
- Fixed cash management (no over-leverage)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import config
from strategy import DataLoader, MomentumScorer, VolatilityPositionSizer
from backtest import PerformanceAnalyzer

# ============================================================================
# DECLINE PREDICTOR
# ============================================================================

class DeclinePredictor:
    """Predict if a stock will decline next month"""

    def __init__(self, prices):
        self.prices = prices

    def predict_declines(self, current_date):
        """
        Return list of tickers predicted to decline

        Decline signals:
        - Negative 3-month momentum
        - Price below 10-month MA
        - Weakening trend (6-month return < 3-month return)
        """

        # Get historical data up to current date
        hist_prices = self.prices.loc[:current_date]

        if len(hist_prices) < 252:  # Need at least 1 year of data
            return []

        decline_tickers = []

        for ticker in hist_prices.columns:
            series = hist_prices[ticker].dropna()

            if len(series) < 63:  # Need at least 3 months
                continue

            current_price = series.iloc[-1]

            # Signal 1: Negative 3-month momentum
            if len(series) >= 63:
                mom_3m = (current_price / series.iloc[-63] - 1) if series.iloc[-63] > 0 else 0
                signal_1 = mom_3m < -0.05  # Down more than 5% in 3 months
            else:
                signal_1 = False

            # Signal 2: Price below 10-month MA
            if len(series) >= 210:
                ma_10m = series.iloc[-210:].mean()
                signal_2 = current_price < ma_10m
            else:
                signal_2 = False

            # Signal 3: Weakening trend (recent momentum worse than medium-term)
            if len(series) >= 126:
                mom_6m = (current_price / series.iloc[-126] - 1) if series.iloc[-126] > 0 else 0
                mom_1m = (current_price / series.iloc[-21] - 1) if series.iloc[-21] > 0 else 0
                signal_3 = mom_1m < mom_6m - 0.1  # Recent momentum significantly weaker
            else:
                signal_3 = False

            # Predict decline if at least 2 signals triggered
            if sum([signal_1, signal_2, signal_3]) >= 2:
                decline_tickers.append(ticker)

        return decline_tickers


# ============================================================================
# AGGRESSIVE BACKTEST ENGINE V2
# ============================================================================

class AggressiveBacktesterV2:
    """Backtest with smart profit-taking: sell only if profitable AND predicted decline"""

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
            print("AGGRESSIVE BACKTEST V2 EXECUTION")
            print("=" * 80)
            print(f"\nPeriod: {self.start_date} -> {self.end_date}")
            print(f"Universe: {len(self.tickers)} tickers")
            print(f"Initial capital: ${self.initial_capital:,.0f}")
            print(f"\nStrategy:")
            print(f"  1. Predict top momentum stocks each month")
            print(f"  2. SELL only if: (a) In PROFIT + (b) Predict DECLINE")
            print(f"  3. HOLD all losers until recovery")
            print(f"  4. HOLD winners if still strong")
            print(f"  5. Fixed cash management (no leverage)\n")

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
        decline_predictor = DeclinePredictor(prices)

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

            # Predict which stocks will decline
            predicted_declines = decline_predictor.predict_declines(date)

            # Get current prices
            current_prices = monthly_prices.loc[date]

            # Update portfolio value first (mark-to-market existing positions)
            current_position_value = (positions * current_prices).sum()
            portfolio_value = current_position_value + cash

            # Calculate available capital (keep cash buffer as percentage)
            cash_buffer_pct = config.MIN_CASH_BUFFER
            available_capital = portfolio_value * (1 - cash_buffer_pct)

            # SMART REBALANCE: Only sell profitable positions predicted to decline
            new_positions, trades_made, new_cash = self._smart_rebalance(
                positions, target_weights, current_prices, cash,
                portfolio_value, date, predicted_declines
            )

            positions = new_positions
            cash = new_cash
            self.trades.extend(trades_made)

            # Update portfolio value after rebalancing
            position_value = (positions * current_prices).sum()
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
            print(f"   Final Cash: ${cash:,.0f}")
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

    def _smart_rebalance(self, current_positions, target_weights, prices, cash,
                         portfolio_value, date, predicted_declines):
        """
        SMART REBALANCING LOGIC:
        1. For existing positions:
           - If profitable AND predicted to decline -> SELL (take profit)
           - Otherwise -> HOLD (all losers, and winners not declining)
        2. Use available cash to buy top predictions
        3. Never go negative on cash (strict constraint)
        """

        trades = []
        new_positions = current_positions.copy()
        current_cash = cash

        # PHASE 1: Evaluate existing positions (sell decisions)
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

            # SMART SELL DECISION: Only if BOTH conditions met
            is_profitable = pnl_pct > 0.03  # At least 3% profit
            is_declining = ticker in predicted_declines

            if is_profitable and is_declining:
                # TAKE PROFIT - sell because we predict decline
                sell_value = current_shares * current_price
                current_cash += sell_value

                trades.append({
                    'date': date,
                    'ticker': ticker,
                    'action': 'TAKE_PROFIT',
                    'shares': current_shares,
                    'price': current_price,
                    'value': sell_value,
                    'pnl_pct': pnl_pct,
                    'reason': 'PROFIT_AND_PREDICT_DECLINE'
                })
                new_positions[ticker] = 0
                if ticker in self.cost_basis:
                    del self.cost_basis[ticker]
            else:
                # HOLD - either not profitable, or still strong
                reason = 'HOLD_LOSER' if pnl_pct < 0 else 'HOLD_WINNER_STRONG'
                trades.append({
                    'date': date,
                    'ticker': ticker,
                    'action': 'HOLD',
                    'shares': current_shares,
                    'price': current_price,
                    'value': current_shares * current_price,
                    'pnl_pct': pnl_pct,
                    'reason': reason
                })

        # PHASE 2: Buy new positions with available cash
        # Calculate how much we can invest
        cash_buffer_pct = config.MIN_CASH_BUFFER
        available_for_investment = current_cash * (1 - cash_buffer_pct)

        if available_for_investment > 100:  # Only buy if we have meaningful cash
            # Calculate target allocation for new buys
            target_dollars = target_weights * portfolio_value

            # Sort by weight (buy highest conviction first)
            sorted_targets = target_dollars.sort_values(ascending=False)

            for ticker in sorted_targets.index:
                if available_for_investment < 100:  # Out of cash
                    break

                price = prices.get(ticker, np.nan)
                if pd.isna(price) or price <= 0:
                    continue

                target_value = sorted_targets[ticker]
                current_shares = new_positions.get(ticker, 0)
                current_value = current_shares * price

                # Calculate how much more we need
                value_to_buy = max(0, target_value - current_value)

                # Limit to available cash
                value_to_buy = min(value_to_buy, available_for_investment)

                if value_to_buy > 100:  # Minimum trade size
                    shares_to_buy = int(value_to_buy / price)
                    actual_cost = shares_to_buy * price

                    if actual_cost <= available_for_investment:
                        # Execute buy
                        current_cash -= actual_cost
                        available_for_investment -= actual_cost

                        old_shares = new_positions.get(ticker, 0)
                        new_total_shares = old_shares + shares_to_buy

                        # Update cost basis (weighted average)
                        if old_shares > 0:
                            old_basis = self.cost_basis.get(ticker, price)
                            old_value = old_shares * old_basis
                            new_value = shares_to_buy * price
                            self.cost_basis[ticker] = (old_value + new_value) / new_total_shares
                            action = 'BUY_MORE'
                        else:
                            self.cost_basis[ticker] = price
                            action = 'BUY_NEW'

                        new_positions[ticker] = new_total_shares

                        trades.append({
                            'date': date,
                            'ticker': ticker,
                            'action': action,
                            'shares': shares_to_buy,
                            'price': price,
                            'value': actual_cost,
                            'pnl_pct': 0.0,
                            'reason': 'TOP_PREDICTION'
                        })

        # Remove zero positions
        new_positions = new_positions[new_positions > 0]

        return new_positions, trades, current_cash


# ============================================================================
# RUN BACKTESTS
# ============================================================================

if __name__ == '__main__':
    print("\n" + "="*80)
    print("AGGRESSIVE MOMENTUM STRATEGY V2 - COMPARISON BACKTESTS")
    print("="*80)
    print("\nSmart Profit-Taking Rules:")
    print("  1. SELL only if BOTH:")
    print("     - Position is profitable (>2% gain)")
    print("     - Predicted to decline (2+ negative signals)")
    print("  2. HOLD everything else:")
    print("     - All losing positions (wait for recovery)")
    print("     - Winning positions still strong (let winners run)")
    print("  3. BUY top momentum predictions with available cash")
    print("  4. Never exceed available capital (no leverage)\n")

    # ========================================================================
    # TEST 1: 8-Year Backtest (2016-2023)
    # ========================================================================

    print("=" * 80)
    print("TEST 1: 8-YEAR BACKTEST (2016-2023)")
    print("=" * 80)

    backtester_8yr = AggressiveBacktesterV2(
        universe_tickers=config.TOP_500_COMMON_STOCKS,
        start_date='2016-01-01',
        end_date='2023-12-31',
        initial_capital=100000
    )

    results_8yr = backtester_8yr.run(verbose=True)

    analyzer_8yr = PerformanceAnalyzer(
        returns=results_8yr['returns'],
        benchmark_returns=results_8yr['benchmark_returns'],
        equity_curve=results_8yr['equity_curve'],
        trades=results_8yr['trades'],
    )

    metrics_8yr = analyzer_8yr.calculate_all_metrics()

    print("PERFORMANCE METRICS (8 Years: 2016-2023)")
    print("=" * 80)
    print(f"{'Metric':<25} {'V2 Strategy':>15}")
    print("-" * 80)
    print(f"{'Total Return':<25} {metrics_8yr['total_return']:>14.2%}")
    print(f"{'CAGR':<25} {metrics_8yr['cagr']:>14.2%}")
    print(f"{'Volatility':<25} {metrics_8yr['volatility']:>14.2%}")
    print(f"{'Sharpe Ratio':<25} {metrics_8yr['sharpe_ratio']:>14.2f}")
    print(f"{'Max Drawdown':<25} {metrics_8yr['max_drawdown']:>14.2%}")
    print(f"{'Win Rate':<25} {metrics_8yr.get('win_rate', 0):>14.2%}")
    print(f"{'Total Trades':<25} {metrics_8yr.get('num_trades', 0):>15.0f}")
    print("=" * 80)

    # Analyze trades
    if not results_8yr['trades'].empty:
        trades_df = results_8yr['trades']
        print(f"\nTrade Analysis (8-year):")
        print(f"  Total trades: {len(trades_df)}")
        if 'reason' in trades_df.columns:
            print(f"\n  By Action:")
            for reason, count in trades_df['reason'].value_counts().head(10).items():
                print(f"    {reason:<30}: {count:>5} trades")

    # ========================================================================
    # TEST 2: Recent Period (2024-2025)
    # ========================================================================

    print("\n\n" + "=" * 80)
    print("TEST 2: RECENT PERIOD (2024-2025)")
    print("=" * 80)

    backtester_recent = AggressiveBacktesterV2(
        universe_tickers=config.TOP_500_COMMON_STOCKS,
        start_date='2024-01-01',
        end_date='2025-12-31',
        initial_capital=100000
    )

    results_recent = backtester_recent.run(verbose=True)

    analyzer_recent = PerformanceAnalyzer(
        returns=results_recent['returns'],
        benchmark_returns=results_recent['benchmark_returns'],
        equity_curve=results_recent['equity_curve'],
        trades=results_recent['trades'],
    )

    metrics_recent = analyzer_recent.calculate_all_metrics()

    print("PERFORMANCE METRICS (Recent: 2024-2025)")
    print("=" * 80)
    print(f"{'Metric':<25} {'V2 Strategy':>15}")
    print("-" * 80)
    print(f"{'Total Return':<25} {metrics_recent['total_return']:>14.2%}")
    print(f"{'CAGR':<25} {metrics_recent['cagr']:>14.2%}")
    print(f"{'Volatility':<25} {metrics_recent['volatility']:>14.2%}")
    print(f"{'Sharpe Ratio':<25} {metrics_recent['sharpe_ratio']:>14.2f}")
    print(f"{'Max Drawdown':<25} {metrics_recent['max_drawdown']:>14.2%}")
    print(f"{'Win Rate':<25} {metrics_recent.get('win_rate', 0):>14.2%}")
    print(f"{'Total Trades':<25} {metrics_recent.get('num_trades', 0):>15.0f}")
    print("=" * 80)
