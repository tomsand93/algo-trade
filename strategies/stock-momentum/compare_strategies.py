"""
STRATEGY COMPARISON: Aggressive V2 vs Simple_analist
====================================================
Compare both strategies on same time periods with visualizations
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import sys
import os

# Import aggressive V2
sys.path.insert(0, r"C:\Users\Tom1\Desktop\TRADING\production\stock_momentum")
import config
from backtest_aggressive_v2 import AggressiveBacktesterV2
from backtest import PerformanceAnalyzer

# ============================================================================
# SIMPLE ANALIST STRATEGY (Simplified version for comparison)
# ============================================================================

import yfinance as yf

class SimpleAnalistStrategy:
    """Simple_analist strategy implementation"""

    def __init__(self, tickers, start_date, end_date, initial_capital=100000):
        self.tickers = tickers
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital

        # Thresholds
        self.BUY_THRESHOLD = 75
        self.HOLD_THRESHOLD = 55
        self.CASH_BUFFER = 0.05

    def run(self, verbose=True):
        if verbose:
            print("\n" + "=" * 80)
            print("SIMPLE ANALIST STRATEGY")
            print("=" * 80)
            print(f"\nPeriod: {self.start_date} -> {self.end_date}")
            print(f"Universe: {len(self.tickers)} tickers")
            print(f"\nStrategy:")
            print(f"  - Score stocks 0-100 (fundamental + technical)")
            print(f"  - BUY if score >= 75")
            print(f"  - HOLD if score >= 55")
            print(f"  - SELL if score < 55")
            print(f"  - Equal-weight portfolio + 5% cash buffer\n")

        # Download data
        if verbose:
            print("[1/4] Downloading price data...")

        series = {}
        for ticker in self.tickers:
            try:
                data = yf.download(ticker, start=self.start_date, auto_adjust=True, progress=False, threads=False)
                if not data.empty and len(data) > 50:
                    if 'Close' in data.columns:
                        close = data['Close']
                    else:
                        continue
                    if isinstance(close, pd.DataFrame):
                        close = close.iloc[:, 0]
                    close = close.dropna()
                    close.name = ticker
                    series[ticker] = close
            except:
                continue

        prices = pd.concat(series.values(), axis=1)
        prices.columns = list(series.keys())
        prices = prices.sort_index()

        if verbose:
            print(f"   [OK] Loaded {len(prices.columns)} tickers, {len(prices)} days")

        # Resample to monthly
        if verbose:
            print("[2/4] Calculating scores...")
        monthly_prices = prices.resample("ME").last()
        monthly_returns = monthly_prices.pct_change(fill_method=None)
        monthly_idx = monthly_prices.index

        # Calculate scores
        tickers_ok = [t for t in self.tickers if t in monthly_prices.columns]

        scores = pd.DataFrame(index=monthly_idx, columns=tickers_ok, dtype=float)

        for ticker in tickers_ok:
            series = monthly_prices[ticker]

            # Fundamental score (YoY growth)
            yoy = series.pct_change(12, fill_method=None)
            fundamental = pd.Series(10.0, index=series.index)
            fundamental[yoy > 0.15] = 40.0
            fundamental[(yoy > 0.05) & (yoy <= 0.15)] = 25.0

            # Technical score
            ma = series.rolling(10).mean()
            mom = series.pct_change(3, fill_method=None)
            technical = (series > ma).astype(int) * 10 + (mom > 0).astype(int) * 10

            # Combined
            raw_score = fundamental + technical
            scores[ticker] = (raw_score / 60.0) * 100.0

        # Generate recommendations
        recommendations = scores.applymap(lambda x: "BUY" if x >= self.BUY_THRESHOLD
                                          else ("HOLD" if x >= self.HOLD_THRESHOLD else "SELL"))

        # Convert to positions
        if verbose:
            print("[3/4] Simulating trades...")
        positions = pd.DataFrame(0.0, index=monthly_idx, columns=tickers_ok)

        for ticker in tickers_ok:
            pos = []
            current = 0.0
            for date in monthly_idx:
                rec = recommendations.loc[date, ticker]
                if rec == "BUY":
                    current = 1.0
                elif rec == "SELL":
                    current = 0.0
                # HOLD keeps current
                pos.append(current)
            positions[ticker] = pos

        # Shift positions (trade at month-end, position applies next month)
        positions_shifted = positions.shift(1).fillna(0.0)

        # Calculate portfolio returns
        stock_returns = positions_shifted * monthly_returns[tickers_ok]

        # Equal-weight with cash buffer
        weights = positions_shifted.div(positions_shifted.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
        weights_buffered = weights * (1 - self.CASH_BUFFER)
        portfolio_returns = (weights_buffered * monthly_returns[tickers_ok]).sum(axis=1)

        # Build equity curve
        if verbose:
            print("[4/4] Calculating performance...")
        equity = (1 + portfolio_returns.fillna(0)).cumprod() * self.initial_capital

        equity_df = pd.DataFrame({
            'portfolio_value': equity,
            'date': equity.index
        }).set_index('date')

        if verbose:
            print("   [OK] Complete\n")
            print("=" * 80 + "\n")

        return {
            'equity_curve': equity_df,
            'returns': portfolio_returns,
            'final_value': equity.iloc[-1]
        }


# ============================================================================
# RUN COMPARISONS
# ============================================================================

def run_comparison(start_date, end_date, period_name):
    """Run both strategies and compare"""

    print("\n" + "="*80)
    print(f"COMPARISON: {period_name}")
    print("="*80)

    # Strategy 1: Aggressive V2
    print("\n" + "-"*80)
    print("STRATEGY 1: AGGRESSIVE V2 (Profit + Predict Decline)")
    print("-"*80)

    agg = AggressiveBacktesterV2(
        universe_tickers=config.DEFAULT_UNIVERSE,
        start_date=start_date,
        end_date=end_date,
        initial_capital=100000
    )

    results_agg = agg.run(verbose=True)

    # Strategy 2: Simple Analist
    print("\n" + "-"*80)
    print("STRATEGY 2: SIMPLE ANALIST (Score-Based BUY/HOLD/SELL)")
    print("-"*80)

    # Use larger universe for Simple Analist (it was designed for more stocks)
    simple_universe = list(set(config.DEFAULT_UNIVERSE + [
        "AAPL", "MSFT", "GOOGL", "META", "NVDA", "TSLA", "AMD", "INTC",
        "JPM", "BAC", "GS", "MS", "BRK-B", "JNJ", "XOM", "WMT", "COST"
    ]))

    simple = SimpleAnalistStrategy(
        tickers=simple_universe,
        start_date=start_date,
        end_date=end_date,
        initial_capital=100000
    )

    results_simple = simple.run(verbose=True)

    # Calculate metrics for both
    # For Aggressive V2
    analyzer_agg = PerformanceAnalyzer(
        returns=results_agg['returns'],
        benchmark_returns=results_agg['benchmark_returns'],
        equity_curve=results_agg['equity_curve'],
        trades=results_agg['trades'],
    )
    metrics_agg = analyzer_agg.calculate_all_metrics()

    # For Simple Analist
    returns_simple = results_simple['returns']
    total_return_simple = (results_simple['equity_curve']['portfolio_value'].iloc[-1] /
                           results_simple['equity_curve']['portfolio_value'].iloc[0]) - 1
    years_simple = len(returns_simple) / 12
    cagr_simple = (1 + total_return_simple) ** (1 / years_simple) - 1
    volatility_simple = returns_simple.std() * np.sqrt(12)
    sharpe_simple = cagr_simple / volatility_simple if volatility_simple > 0 else 0

    # Max drawdown
    equity_simple = results_simple['equity_curve']['portfolio_value']
    running_max = equity_simple.cummax()
    drawdown_simple = (equity_simple / running_max - 1).min()

    # Print comparison
    print("\n" + "="*80)
    print(f"PERFORMANCE COMPARISON: {period_name}")
    print("="*80)
    print(f"\n{'Metric':<25} {'Aggressive V2':>15} {'Simple Analist':>18} {'Winner':>12}")
    print("-" * 80)
    print(f"{'Total Return':<25} {metrics_agg['total_return']:>14.2%} {total_return_simple:>17.2%} {'  ' + ('Agg' if metrics_agg['total_return'] > total_return_simple else 'Simple'):>12}")
    print(f"{'CAGR':<25} {metrics_agg['cagr']:>14.2%} {cagr_simple:>17.2%} {'  ' + ('Agg' if metrics_agg['cagr'] > cagr_simple else 'Simple'):>12}")
    print(f"{'Volatility':<25} {metrics_agg['volatility']:>14.2%} {volatility_simple:>17.2%} {'  ' + ('Simple' if volatility_simple < metrics_agg['volatility'] else 'Agg'):>12}")
    print(f"{'Sharpe Ratio':<25} {metrics_agg['sharpe_ratio']:>14.2f} {sharpe_simple:>17.2f} {'  ' + ('Agg' if metrics_agg['sharpe_ratio'] > sharpe_simple else 'Simple'):>12}")
    print(f"{'Max Drawdown':<25} {metrics_agg['max_drawdown']:>14.2%} {drawdown_simple:>17.2%} {'  ' + ('Simple' if drawdown_simple > metrics_agg['max_drawdown'] else 'Agg'):>12}")
    print(f"{'Final Value':<25} ${results_agg['final_value']:>13,.0f} ${results_simple['final_value']:>16,.0f} {'  ' + ('Agg' if results_agg['final_value'] > results_simple['final_value'] else 'Simple'):>12}")
    print("="*80)

    return results_agg, results_simple, metrics_agg


# ============================================================================
# CREATE VISUALIZATIONS
# ============================================================================

def create_comparison_charts(results_agg, results_simple, period_name):
    """Create comparison charts"""

    fig, axes = plt.subplots(3, 1, figsize=(14, 12))
    fig.suptitle(f'Strategy Comparison: {period_name}', fontsize=16, fontweight='bold')

    # Chart 1: Equity Curves
    ax1 = axes[0]
    equity_agg = results_agg['equity_curve']['portfolio_value']
    equity_simple = results_simple['equity_curve']['portfolio_value']

    # Normalize to 100
    equity_agg_norm = equity_agg / equity_agg.iloc[0] * 100
    equity_simple_norm = equity_simple / equity_simple.iloc[0] * 100

    ax1.plot(equity_agg_norm.index, equity_agg_norm.values,
             label='Aggressive V2', linewidth=2, color='#2E86AB')
    ax1.plot(equity_simple_norm.index, equity_simple_norm.values,
             label='Simple Analist', linewidth=2, color='#A23B72', linestyle='--')
    ax1.axhline(y=100, color='gray', linestyle=':', alpha=0.5)
    ax1.set_title('Equity Curve (Normalized to 100)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Portfolio Value')
    ax1.legend(loc='best')
    ax1.grid(alpha=0.3)

    # Chart 2: Monthly Returns
    ax2 = axes[1]
    returns_agg = results_agg['returns']
    returns_simple = results_simple['returns']

    # Align dates
    common_dates = returns_agg.index.intersection(returns_simple.index)

    x = np.arange(len(common_dates))
    width = 0.35

    ax2.bar(x - width/2, returns_agg.loc[common_dates].values * 100, width,
            label='Aggressive V2', color='#2E86AB', alpha=0.7)
    ax2.bar(x + width/2, returns_simple.loc[common_dates].values * 100, width,
            label='Simple Analist', color='#A23B72', alpha=0.7)
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
    ax2.set_title('Monthly Returns Comparison', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Monthly Return (%)')
    ax2.set_xticks([])
    ax2.legend(loc='best')
    ax2.grid(alpha=0.3, axis='y')

    # Chart 3: Drawdown
    ax3 = axes[2]

    # Calculate drawdowns
    running_max_agg = equity_agg.cummax()
    drawdown_agg = (equity_agg / running_max_agg - 1) * 100

    running_max_simple = equity_simple.cummax()
    drawdown_simple = (equity_simple / running_max_simple - 1) * 100

    ax3.fill_between(drawdown_agg.index, drawdown_agg.values, 0,
                     label='Aggressive V2', color='#2E86AB', alpha=0.4)
    ax3.fill_between(drawdown_simple.index, drawdown_simple.values, 0,
                     label='Simple Analist', color='#A23B72', alpha=0.4)
    ax3.set_title('Drawdown Comparison', fontsize=12, fontweight='bold')
    ax3.set_ylabel('Drawdown (%)')
    ax3.set_xlabel('Date')
    ax3.legend(loc='best')
    ax3.grid(alpha=0.3)

    plt.tight_layout()

    # Save figure
    filename = f"strategy_comparison_{period_name.replace(' ', '_').replace('-', '_')}.png"
    filepath = os.path.join(r"C:\Users\Tom1\Desktop\TRADING\production\stock_momentum", filename)
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    print(f"\n[OK] Chart saved: {filepath}")

    plt.show()

    return filepath


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == '__main__':
    # Test 1: 2022-2023 (Bear market period)
    print("\n" + "="*80)
    print("=" + " "*78 + "=")
    print("=" + "  STRATEGY SHOWDOWN: Aggressive V2 vs Simple Analist".center(78) + "=")
    print("=" + " "*78 + "=")
    print("="*80)

    results_agg_1, results_simple_1, metrics_agg_1 = run_comparison(
        '2022-01-01', '2023-12-31', '2022-2023 (Bear Market)'
    )

    chart1 = create_comparison_charts(results_agg_1, results_simple_1, '2022-2023 Bear Market')

    # Test 2: 2024-2025 (Recent period)
    results_agg_2, results_simple_2, metrics_agg_2 = run_comparison(
        '2024-01-01', '2025-12-31', '2024-2025 (Recent)'
    )

    chart2 = create_comparison_charts(results_agg_2, results_simple_2, '2024-2025 Recent')

    print("\n" + "="*80)
    print("COMPARISON COMPLETE!")
    print("="*80)
    print(f"\n[OK] All charts generated and saved")
    print(f"   - {chart1}")
    print(f"   - {chart2}")
