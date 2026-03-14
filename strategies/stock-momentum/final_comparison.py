"""
ULTIMATE STRATEGY COMPARISON (2016-2025)
========================================
Compare 3 strategies on SAME universe:
1. Aggressive V2 (momentum-based, hold losers)
2. Simple_analist (score-based BUY/HOLD/SELL)
3. HYBRID (Simple scoring + Aggressive exits)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import yfinance as yf

# ============================================================================
# SHARED UNIVERSE (Expanded to 50 stocks for fair comparison)
# ============================================================================

SHARED_UNIVERSE = [
    # Tech giants
    "AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD", "INTC", "TSLA",
    "AMZN", "NFLX", "ADBE", "ORCL", "IBM",
    # Finance
    "JPM", "BAC", "GS", "MS", "BRK-B", "BLK",
    # Consumer
    "WMT", "COST", "KO", "PEP", "JNJ", "PFE", "UNH",
    # Energy
    "XOM", "CVX",
    # Industrial/Defense
    "BA", "LMT", "NOC", "RTX", "GD",
    # ETFs for diversification
    "QQQ", "SPY", "IWM", "DIA", "XLF", "XLE", "XLK", "XLV", "XLI", "XLY",
    # Semiconductors
    "AVGO", "MU", "NXPI", "ASML", "TSM",
]

BENCHMARK = "SPY"
INITIAL_CAPITAL = 100000

# ============================================================================
# STRATEGY 1: AGGRESSIVE V2
# ============================================================================

class AggressiveV2Strategy:
    """Aggressive V2: Momentum-based, hold losers, sell profitable decliners"""

    def __init__(self, universe, start_date, end_date):
        self.universe = universe
        self.start_date = start_date
        self.end_date = end_date
        self.cost_basis = {}
        self.CASH_BUFFER = 0.05

    def run(self, prices, verbose=True):
        if verbose:
            print("\n[AGGRESSIVE V2] Running backtest...")

        monthly_prices = prices.resample("ME").last()
        monthly_returns = monthly_prices.pct_change(fill_method=None)
        dates = monthly_prices.index

        # Initialize
        portfolio_value = INITIAL_CAPITAL
        positions = pd.Series(dtype=float)
        cash = INITIAL_CAPITAL
        equity_curve = []

        for i, date in enumerate(dates):
            # Calculate momentum scores
            scores = self._calculate_momentum_scores(prices.loc[:date], monthly_prices.loc[:date])

            # Get top stocks
            top_stocks = scores.nlargest(15).index.tolist()

            # Current prices
            current_prices = monthly_prices.loc[date]

            # Mark to market
            position_value = (positions * current_prices).sum()
            portfolio_value = position_value + cash

            # Predict declines
            declines = self._predict_declines(prices.loc[:date], date)

            # Rebalance
            positions, cash = self._rebalance(
                positions, top_stocks, current_prices, cash,
                portfolio_value, declines
            )

            # Update portfolio
            position_value = (positions * current_prices).sum()
            portfolio_value = position_value + cash

            equity_curve.append({'date': date, 'value': portfolio_value})

        equity_df = pd.DataFrame(equity_curve).set_index('date')
        returns = equity_df['value'].pct_change().dropna()

        return {'equity': equity_df, 'returns': returns}

    def _calculate_momentum_scores(self, prices, monthly_prices):
        scores = pd.Series(dtype=float)
        for ticker in self.universe:
            if ticker not in prices.columns:
                continue
            series = prices[ticker].dropna()
            if len(series) < 126:
                continue

            # Multi-factor momentum
            mom_3m = (series.iloc[-1] / series.iloc[-63] - 1) if len(series) >= 63 else 0
            mom_6m = (series.iloc[-1] / series.iloc[-126] - 1) if len(series) >= 126 else 0
            mom_12m = (series.iloc[-1] / series.iloc[-252] - 1) if len(series) >= 252 else 0

            score = mom_3m * 0.3 + mom_6m * 0.4 + mom_12m * 0.3
            scores[ticker] = score

        return scores.sort_values(ascending=False)

    def _predict_declines(self, prices, date):
        declines = []
        for ticker in self.universe:
            if ticker not in prices.columns:
                continue
            series = prices[ticker].dropna()
            if len(series) < 63:
                continue

            current = series.iloc[-1]
            mom_3m = (current / series.iloc[-63] - 1) if len(series) >= 63 else 0
            ma_10m = series.iloc[-210:].mean() if len(series) >= 210 else current

            if mom_3m < -0.05 and current < ma_10m:
                declines.append(ticker)

        return declines

    def _rebalance(self, positions, targets, prices, cash, portfolio_value, declines):
        new_positions = positions.copy()

        # Phase 1: Sell decisions
        for ticker in positions.index:
            if positions[ticker] <= 0:
                continue
            current_price = prices.get(ticker, np.nan)
            if pd.isna(current_price):
                continue

            cost = self.cost_basis.get(ticker, current_price)
            pnl = (current_price - cost) / cost

            # Sell if profitable AND predicted decline
            if pnl > 0.02 and ticker in declines:
                cash += positions[ticker] * current_price
                new_positions[ticker] = 0
                if ticker in self.cost_basis:
                    del self.cost_basis[ticker]

        # Phase 2: Buy targets
        available = cash * (1 - self.CASH_BUFFER)
        target_weight = 1.0 / len(targets) if targets else 0

        for ticker in targets:
            if available < 100:
                break
            price = prices.get(ticker, np.nan)
            if pd.isna(price) or price <= 0:
                continue

            target_value = portfolio_value * target_weight * (1 - self.CASH_BUFFER)
            current_value = new_positions.get(ticker, 0) * price
            value_to_buy = max(0, target_value - current_value)
            value_to_buy = min(value_to_buy, available)

            if value_to_buy > 100:
                shares = int(value_to_buy / price)
                cost_actual = shares * price

                if cost_actual <= available:
                    old_shares = new_positions.get(ticker, 0)
                    new_shares = old_shares + shares

                    if old_shares > 0:
                        old_cost = self.cost_basis.get(ticker, price)
                        self.cost_basis[ticker] = (old_shares * old_cost + shares * price) / new_shares
                    else:
                        self.cost_basis[ticker] = price

                    new_positions[ticker] = new_shares
                    cash -= cost_actual
                    available -= cost_actual

        new_positions = new_positions[new_positions > 0]
        return new_positions, cash


# ============================================================================
# STRATEGY 2: SIMPLE ANALIST
# ============================================================================

class SimpleAnalistStrategy:
    """Simple_analist: Score-based BUY/HOLD/SELL"""

    def __init__(self, universe, start_date, end_date):
        self.universe = universe
        self.start_date = start_date
        self.end_date = end_date
        self.BUY_THRESHOLD = 75
        self.HOLD_THRESHOLD = 55
        self.CASH_BUFFER = 0.05

    def run(self, prices, verbose=True):
        if verbose:
            print("\n[SIMPLE ANALIST] Running backtest...")

        monthly_prices = prices.resample("ME").last()
        monthly_returns = monthly_prices.pct_change(fill_method=None)
        dates = monthly_prices.index

        # Calculate scores
        scores = pd.DataFrame(index=dates, columns=self.universe, dtype=float)

        for ticker in self.universe:
            if ticker not in monthly_prices.columns:
                continue
            series = monthly_prices[ticker]

            # Fundamental: YoY growth
            yoy = series.pct_change(12, fill_method=None)
            fundamental = pd.Series(10.0, index=series.index)
            fundamental[yoy > 0.15] = 40.0
            fundamental[(yoy > 0.05) & (yoy <= 0.15)] = 25.0

            # Technical: MA + momentum
            ma = series.rolling(10).mean()
            mom = series.pct_change(3, fill_method=None)
            technical = (series > ma).astype(int) * 10 + (mom > 0).astype(int) * 10

            raw_score = fundamental + technical
            scores[ticker] = (raw_score / 60.0) * 100.0

        # Generate positions
        positions = pd.DataFrame(0.0, index=dates, columns=self.universe)

        for ticker in self.universe:
            if ticker not in scores.columns:
                continue

            pos = []
            current = 0.0
            for date in dates:
                score = scores.loc[date, ticker]
                if score >= self.BUY_THRESHOLD:
                    current = 1.0
                elif score < self.HOLD_THRESHOLD:
                    current = 0.0
                # else HOLD (keep current)
                pos.append(current)
            positions[ticker] = pos

        # Shift positions
        positions_shifted = positions.shift(1).fillna(0.0)

        # Calculate returns
        stock_returns = positions_shifted * monthly_returns[self.universe]
        weights = positions_shifted.div(positions_shifted.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
        weights_buffered = weights * (1 - self.CASH_BUFFER)
        portfolio_returns = (weights_buffered * monthly_returns[self.universe]).sum(axis=1)

        equity = (1 + portfolio_returns.fillna(0)).cumprod() * INITIAL_CAPITAL
        equity_df = pd.DataFrame({'value': equity})

        return {'equity': equity_df, 'returns': portfolio_returns}


# ============================================================================
# STRATEGY 3: HYBRID
# ============================================================================

class HybridStrategy:
    """HYBRID: Simple_analist scoring + Aggressive V2 exits"""

    def __init__(self, universe, start_date, end_date):
        self.universe = universe
        self.start_date = start_date
        self.end_date = end_date
        self.BUY_THRESHOLD = 75
        self.CASH_BUFFER = 0.05
        self.cost_basis = {}

    def run(self, prices, verbose=True):
        if verbose:
            print("\n[HYBRID] Running backtest...")

        monthly_prices = prices.resample("ME").last()
        monthly_returns = monthly_prices.pct_change(fill_method=None)
        dates = monthly_prices.index

        # Initialize
        portfolio_value = INITIAL_CAPITAL
        positions = pd.Series(dtype=float)
        cash = INITIAL_CAPITAL
        equity_curve = []

        for i, date in enumerate(dates):
            # Calculate Simple_analist scores
            scores = self._calculate_scores(monthly_prices.loc[:date])

            # Get top stocks (score >= 75)
            buy_signals = scores[scores >= self.BUY_THRESHOLD].index.tolist()

            # Current prices
            current_prices = monthly_prices.loc[date]

            # Mark to market
            position_value = (positions * current_prices).sum()
            portfolio_value = position_value + cash

            # Rebalance with Aggressive V2 exit logic
            positions, cash = self._rebalance_hybrid(
                positions, buy_signals, scores, current_prices,
                cash, portfolio_value
            )

            # Update portfolio
            position_value = (positions * current_prices).sum()
            portfolio_value = position_value + cash

            equity_curve.append({'date': date, 'value': portfolio_value})

        equity_df = pd.DataFrame(equity_curve).set_index('date')
        returns = equity_df['value'].pct_change().dropna()

        return {'equity': equity_df, 'returns': returns}

    def _calculate_scores(self, monthly_prices):
        scores = pd.Series(dtype=float)

        for ticker in self.universe:
            if ticker not in monthly_prices.columns:
                continue
            series = monthly_prices[ticker].dropna()
            if len(series) < 12:
                continue

            # Fundamental: YoY growth
            yoy = series.pct_change(12, fill_method=None).iloc[-1]
            if yoy > 0.15:
                fundamental = 40.0
            elif yoy > 0.05:
                fundamental = 25.0
            else:
                fundamental = 10.0

            # Technical: MA + momentum
            ma = series.rolling(10).mean().iloc[-1]
            mom = series.pct_change(3, fill_method=None).iloc[-1]

            technical = 0
            if series.iloc[-1] > ma:
                technical += 10
            if mom > 0:
                technical += 10

            raw_score = fundamental + technical
            scores[ticker] = (raw_score / 60.0) * 100.0

        return scores

    def _rebalance_hybrid(self, positions, buy_signals, scores, prices, cash, portfolio_value):
        new_positions = positions.copy()

        # Phase 1: Exit decisions (Aggressive V2 logic)
        for ticker in positions.index:
            if positions[ticker] <= 0:
                continue
            current_price = prices.get(ticker, np.nan)
            if pd.isna(current_price):
                continue

            cost = self.cost_basis.get(ticker, current_price)
            pnl = (current_price - cost) / cost
            score = scores.get(ticker, 0)

            # SELL if: profitable AND score dropped below 55 (weak now)
            if pnl > 0.02 and score < 55:
                cash += positions[ticker] * current_price
                new_positions[ticker] = 0
                if ticker in self.cost_basis:
                    del self.cost_basis[ticker]
            # Otherwise HOLD (never sell at loss, hold winners with score >= 55)

        # Phase 2: Buy targets
        available = cash * (1 - self.CASH_BUFFER)
        target_weight = 1.0 / len(buy_signals) if buy_signals else 0

        for ticker in buy_signals:
            if available < 100:
                break
            price = prices.get(ticker, np.nan)
            if pd.isna(price) or price <= 0:
                continue

            target_value = portfolio_value * target_weight * (1 - self.CASH_BUFFER)
            current_value = new_positions.get(ticker, 0) * price
            value_to_buy = max(0, target_value - current_value)
            value_to_buy = min(value_to_buy, available)

            if value_to_buy > 100:
                shares = int(value_to_buy / price)
                cost_actual = shares * price

                if cost_actual <= available:
                    old_shares = new_positions.get(ticker, 0)
                    new_shares = old_shares + shares

                    if old_shares > 0:
                        old_cost = self.cost_basis.get(ticker, price)
                        self.cost_basis[ticker] = (old_shares * old_cost + shares * price) / new_shares
                    else:
                        self.cost_basis[ticker] = price

                    new_positions[ticker] = new_shares
                    cash -= cost_actual
                    available -= cost_actual

        new_positions = new_positions[new_positions > 0]
        return new_positions, cash


# ============================================================================
# DATA LOADER
# ============================================================================

def load_data(universe, start_date, end_date, verbose=True):
    """Load price data for all tickers"""
    if verbose:
        print(f"\n[DATA] Loading {len(universe)} tickers from {start_date} to {end_date}...")

    series = {}
    for ticker in universe:
        try:
            data = yf.download(ticker, start=start_date, end=end_date,
                             auto_adjust=True, progress=False, threads=False)
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
        print(f"[DATA] Loaded {len(prices.columns)} tickers, {len(prices)} days")

    return prices


# ============================================================================
# PERFORMANCE METRICS
# ============================================================================

def calculate_metrics(returns, equity):
    total_return = (equity['value'].iloc[-1] / equity['value'].iloc[0]) - 1
    years = len(returns) / 12
    cagr = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    volatility = returns.std() * np.sqrt(12)
    sharpe = cagr / volatility if volatility > 0 else 0

    running_max = equity['value'].cummax()
    drawdown = (equity['value'] / running_max - 1).min()

    return {
        'total_return': total_return,
        'cagr': cagr,
        'volatility': volatility,
        'sharpe': sharpe,
        'max_drawdown': drawdown,
        'final_value': equity['value'].iloc[-1]
    }


# ============================================================================
# VISUALIZATION
# ============================================================================

def create_comparison_chart(results, period_name):
    """Create comprehensive comparison charts"""

    fig = plt.figure(figsize=(16, 12))
    gs = fig.add_gridspec(4, 2, hspace=0.3, wspace=0.3)

    # Chart 1: Equity Curves
    ax1 = fig.add_subplot(gs[0, :])
    for name, data in results.items():
        equity_norm = data['equity']['value'] / data['equity']['value'].iloc[0] * 100
        ax1.plot(equity_norm.index, equity_norm.values, label=name, linewidth=2.5, alpha=0.9)

    ax1.axhline(y=100, color='gray', linestyle=':', alpha=0.5)
    ax1.set_title(f'Equity Curves - {period_name} (Normalized to 100)', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Portfolio Value', fontsize=11)
    ax1.legend(loc='best', fontsize=10)
    ax1.grid(alpha=0.3)

    # Chart 2: Annual Returns
    ax2 = fig.add_subplot(gs[1, 0])
    annual_returns = {}
    for name, data in results.items():
        returns = data['returns']
        annual = returns.groupby(returns.index.year).apply(lambda x: (1 + x).prod() - 1) * 100
        annual_returns[name] = annual

    years = annual_returns[list(annual_returns.keys())[0]].index
    x = np.arange(len(years))
    width = 0.25

    for i, (name, annual) in enumerate(annual_returns.items()):
        ax2.bar(x + i * width, annual.values, width, label=name, alpha=0.7)

    ax2.set_title('Annual Returns (%)', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Return (%)', fontsize=10)
    ax2.set_xticks(x + width)
    ax2.set_xticklabels(years, rotation=45)
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
    ax2.legend(loc='best', fontsize=9)
    ax2.grid(alpha=0.3, axis='y')

    # Chart 3: Rolling Sharpe Ratio (12-month)
    ax3 = fig.add_subplot(gs[1, 1])
    for name, data in results.items():
        returns = data['returns']
        rolling_sharpe = returns.rolling(12).mean() * 12 / (returns.rolling(12).std() * np.sqrt(12))
        ax3.plot(rolling_sharpe.index, rolling_sharpe.values, label=name, linewidth=2, alpha=0.8)

    ax3.axhline(y=0, color='gray', linestyle=':', alpha=0.5)
    ax3.set_title('Rolling 12-Month Sharpe Ratio', fontsize=12, fontweight='bold')
    ax3.set_ylabel('Sharpe Ratio', fontsize=10)
    ax3.legend(loc='best', fontsize=9)
    ax3.grid(alpha=0.3)

    # Chart 4: Drawdowns
    ax4 = fig.add_subplot(gs[2, :])
    for name, data in results.items():
        equity = data['equity']['value']
        running_max = equity.cummax()
        drawdown = (equity / running_max - 1) * 100
        ax4.fill_between(drawdown.index, drawdown.values, 0, label=name, alpha=0.4)

    ax4.set_title('Drawdown Comparison', fontsize=12, fontweight='bold')
    ax4.set_ylabel('Drawdown (%)', fontsize=10)
    ax4.legend(loc='best', fontsize=9)
    ax4.grid(alpha=0.3)

    # Chart 5: Metrics Table
    ax5 = fig.add_subplot(gs[3, :])
    ax5.axis('off')

    metrics_data = []
    for name, data in results.items():
        metrics = data['metrics']
        metrics_data.append([
            name,
            f"{metrics['total_return']:.1%}",
            f"{metrics['cagr']:.1%}",
            f"{metrics['volatility']:.1%}",
            f"{metrics['sharpe']:.2f}",
            f"{metrics['max_drawdown']:.1%}",
            f"${metrics['final_value']:,.0f}"
        ])

    table = ax5.table(cellText=metrics_data,
                     colLabels=['Strategy', 'Total Return', 'CAGR', 'Volatility',
                               'Sharpe', 'Max DD', 'Final Value'],
                     cellLoc='center',
                     loc='center',
                     bbox=[0, 0, 1, 1])

    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 2)

    # Color code
    for i in range(len(metrics_data)):
        for j in range(7):
            cell = table[(i+1, j)]
            if i == 0:
                cell.set_facecolor('#E8F4F8')
            elif i == 1:
                cell.set_facecolor('#FCE8F3')
            else:
                cell.set_facecolor('#E8F8E8')

    plt.suptitle(f'ULTIMATE STRATEGY COMPARISON: {period_name}',
                fontsize=16, fontweight='bold', y=0.995)

    filename = f"ultimate_comparison_{period_name.replace(' ', '_').replace('-', '_')}.png"
    filepath = f"C:\\Users\\Tom1\\Desktop\\TRADING\\production\\stock_momentum\\{filename}"
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    print(f"\n[OK] Chart saved: {filepath}")

    plt.show()
    return filepath


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == '__main__':
    print("\n" + "="*80)
    print("=" + " "*78 + "=")
    print("=" + "  ULTIMATE STRATEGY SHOWDOWN (2016-2025)".center(78) + "=")
    print("=" + "  Same Universe | Same Period | Fair Comparison".center(78) + "=")
    print("=" + " "*78 + "=")
    print("="*80)

    # Load data
    prices = load_data(SHARED_UNIVERSE, '2015-01-01', '2025-12-31')

    # Filter to test period
    prices_test = prices.loc['2016-01-01':'2025-12-31']

    # Run all strategies
    print("\n" + "="*80)
    print("RUNNING ALL 3 STRATEGIES ON SAME DATA")
    print("="*80)

    agg = AggressiveV2Strategy(SHARED_UNIVERSE, '2016-01-01', '2025-12-31')
    results_agg = agg.run(prices_test)
    metrics_agg = calculate_metrics(results_agg['returns'], results_agg['equity'])

    simple = SimpleAnalistStrategy(SHARED_UNIVERSE, '2016-01-01', '2025-12-31')
    results_simple = simple.run(prices_test)
    metrics_simple = calculate_metrics(results_simple['returns'], results_simple['equity'])

    hybrid = HybridStrategy(SHARED_UNIVERSE, '2016-01-01', '2025-12-31')
    results_hybrid = hybrid.run(prices_test)
    metrics_hybrid = calculate_metrics(results_hybrid['returns'], results_hybrid['equity'])

    # Compile results
    all_results = {
        'Aggressive V2': {'equity': results_agg['equity'], 'returns': results_agg['returns'], 'metrics': metrics_agg},
        'Simple Analist': {'equity': results_simple['equity'], 'returns': results_simple['returns'], 'metrics': metrics_simple},
        'HYBRID': {'equity': results_hybrid['equity'], 'returns': results_hybrid['returns'], 'metrics': metrics_hybrid}
    }

    # Print comparison
    print("\n" + "="*80)
    print("FINAL RESULTS (2016-2025)")
    print("="*80)
    print(f"\n{'Metric':<20} {'Aggressive V2':>15} {'Simple Analist':>18} {'HYBRID':>15} {'Winner':>12}")
    print("-" * 95)

    metrics = ['total_return', 'cagr', 'volatility', 'sharpe', 'max_drawdown', 'final_value']
    for metric in metrics:
        v1 = metrics_agg[metric]
        v2 = metrics_simple[metric]
        v3 = metrics_hybrid[metric]

        if metric == 'final_value':
            print(f"{metric.replace('_', ' ').title():<20} ${v1:>14,.0f} ${v2:>17,.0f} ${v3:>14,.0f}", end="")
        elif metric in ['total_return', 'cagr', 'volatility', 'max_drawdown']:
            print(f"{metric.replace('_', ' ').title():<20} {v1:>14.2%} {v2:>17.2%} {v3:>14.2%}", end="")
        else:
            print(f"{metric.replace('_', ' ').title():<20} {v1:>14.2f} {v2:>17.2f} {v3:>14.2f}", end="")

        # Determine winner
        if metric in ['total_return', 'cagr', 'sharpe', 'final_value']:
            winner = max([(v1, 'Agg'), (v2, 'Simple'), (v3, 'HYBRID')], key=lambda x: x[0])[1]
        elif metric in ['volatility', 'max_drawdown']:
            winner = min([(abs(v1), 'Agg'), (abs(v2), 'Simple'), (abs(v3), 'HYBRID')], key=lambda x: x[0])[1]
        else:
            winner = '-'

        print(f" {winner:>12}")

    print("="*95)

    # Create charts
    create_comparison_chart(all_results, '2016-2025 (9 Years)')

    print("\n" + "="*80)
    print("COMPARISON COMPLETE!")
    print("="*80)
