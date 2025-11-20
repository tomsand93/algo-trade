"""
Visualization script for backtest results
Creates charts and graphs to analyze performance
"""
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import config


def plot_top_strategies():
    """Plot top strategies comparison"""

    # Load results
    results_path = config.LOG_DIR / "backtest_results.json"

    if not results_path.exists():
        print("No results found. Run backtests first.")
        return

    df = pd.read_json(results_path)

    # Set style
    sns.set_style("darkgrid")
    plt.rcParams['figure.figsize'] = (14, 10)

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    # 1. Top 20 performers
    top_20 = df.nlargest(20, 'total_return_pct')
    ax1 = axes[0, 0]
    colors = ['green' if x > 0 else 'red' for x in top_20['total_return_pct']]
    top_20.plot(x='strategy', y='total_return_pct', kind='barh', ax=ax1, color=colors, legend=False)
    ax1.set_xlabel('Total Return (%)')
    ax1.set_ylabel('Strategy + Asset + Timeframe')
    ax1.set_title('Top 20 Performers by Return %')
    ax1.axvline(x=0, color='black', linestyle='--', linewidth=0.5)

    # Create labels with full config
    labels = [f"{row['strategy']}\n{row['asset']}\n{row['timeframe']}" for _, row in top_20.iterrows()]
    ax1.set_yticklabels(labels, fontsize=7)

    # 2. Strategy comparison (average performance)
    ax2 = axes[0, 1]
    strategy_avg = df.groupby('strategy')['total_return_pct'].mean().sort_values()
    colors = ['green' if x > 0 else 'red' for x in strategy_avg.values]
    strategy_avg.plot(kind='barh', ax=ax2, color=colors)
    ax2.set_xlabel('Average Return (%)')
    ax2.set_ylabel('Strategy')
    ax2.set_title('Average Performance by Strategy')
    ax2.axvline(x=0, color='black', linestyle='--', linewidth=0.5)

    # 3. Sharpe ratio vs Return scatter
    ax3 = axes[1, 0]
    for strategy in df['strategy'].unique():
        strategy_data = df[df['strategy'] == strategy]
        ax3.scatter(strategy_data['sharpe_ratio'], strategy_data['total_return_pct'],
                   label=strategy, alpha=0.6, s=50)

    ax3.set_xlabel('Sharpe Ratio')
    ax3.set_ylabel('Total Return (%)')
    ax3.set_title('Risk-Adjusted Returns (Sharpe vs Return)')
    ax3.axhline(y=0, color='black', linestyle='--', linewidth=0.5)
    ax3.axvline(x=0, color='black', linestyle='--', linewidth=0.5)
    ax3.legend(fontsize=8, loc='best')
    ax3.grid(True, alpha=0.3)

    # 4. Asset performance comparison
    ax4 = axes[1, 1]
    asset_avg = df.groupby('asset')['total_return_pct'].mean().sort_values()
    colors = ['green' if x > 0 else 'red' for x in asset_avg.values]
    asset_avg.plot(kind='barh', ax=ax4, color=colors)
    ax4.set_xlabel('Average Return (%)')
    ax4.set_ylabel('Asset')
    ax4.set_title('Average Performance by Asset')
    ax4.axvline(x=0, color='black', linestyle='--', linewidth=0.5)

    plt.tight_layout()

    # Save figure
    output_path = config.LOG_DIR / "performance_charts.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✓ Saved chart: {output_path}")

    plt.show()


def plot_timeframe_analysis():
    """Analyze performance across different timeframes"""

    results_path = config.LOG_DIR / "backtest_results.json"

    if not results_path.exists():
        print("No results found. Run backtests first.")
        return

    df = pd.read_json(results_path)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Timeframe performance
    ax1 = axes[0]
    timeframe_stats = df.groupby('timeframe').agg({
        'total_return_pct': ['mean', 'std']
    })['total_return_pct']

    x = range(len(timeframe_stats))
    ax1.bar(x, timeframe_stats['mean'], yerr=timeframe_stats['std'],
            capsize=5, alpha=0.7, color='steelblue')
    ax1.set_xticks(x)
    ax1.set_xticklabels(timeframe_stats.index)
    ax1.set_xlabel('Timeframe')
    ax1.set_ylabel('Average Return (%) with Std Dev')
    ax1.set_title('Performance by Timeframe')
    ax1.axhline(y=0, color='black', linestyle='--', linewidth=0.5)
    ax1.grid(True, alpha=0.3, axis='y')

    # Win rate by timeframe
    ax2 = axes[1]
    winrate_by_tf = df.groupby('timeframe')['win_rate'].mean().sort_values()
    winrate_by_tf.plot(kind='barh', ax=ax2, color='coral')
    ax2.set_xlabel('Average Win Rate (%)')
    ax2.set_ylabel('Timeframe')
    ax2.set_title('Win Rate by Timeframe')
    ax2.grid(True, alpha=0.3, axis='x')

    plt.tight_layout()

    output_path = config.LOG_DIR / "timeframe_analysis.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✓ Saved chart: {output_path}")

    plt.show()


def plot_risk_analysis():
    """Analyze performance across risk levels"""

    results_path = config.LOG_DIR / "backtest_results.json"

    if not results_path.exists():
        print("No results found. Run backtests first.")
        return

    df = pd.read_json(results_path)

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # Return by risk level
    ax1 = axes[0]
    risk_returns = df.groupby('risk')['total_return_pct'].mean()
    risk_returns.plot(kind='bar', ax=ax1, color='green', alpha=0.7)
    ax1.set_xlabel('Risk Level (Position Size)')
    ax1.set_ylabel('Average Return (%)')
    ax1.set_title('Returns by Risk Level')
    ax1.set_xticklabels([f"{int(r*100)}%" for r in risk_returns.index], rotation=0)
    ax1.grid(True, alpha=0.3, axis='y')

    # Sharpe ratio by risk level
    ax2 = axes[1]
    risk_sharpe = df.groupby('risk')['sharpe_ratio'].mean()
    risk_sharpe.plot(kind='bar', ax=ax2, color='blue', alpha=0.7)
    ax2.set_xlabel('Risk Level (Position Size)')
    ax2.set_ylabel('Average Sharpe Ratio')
    ax2.set_title('Risk-Adjusted Returns by Risk Level')
    ax2.set_xticklabels([f"{int(r*100)}%" for r in risk_sharpe.index], rotation=0)
    ax2.grid(True, alpha=0.3, axis='y')

    # Max drawdown by risk level
    ax3 = axes[2]
    risk_drawdown = df.groupby('risk')['max_drawdown_pct'].mean()
    risk_drawdown.plot(kind='bar', ax=ax3, color='red', alpha=0.7)
    ax3.set_xlabel('Risk Level (Position Size)')
    ax3.set_ylabel('Average Max Drawdown (%)')
    ax3.set_title('Max Drawdown by Risk Level')
    ax3.set_xticklabels([f"{int(r*100)}%" for r in risk_drawdown.index], rotation=0)
    ax3.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()

    output_path = config.LOG_DIR / "risk_analysis.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✓ Saved chart: {output_path}")

    plt.show()


def generate_all_charts():
    """Generate all visualization charts"""

    print("=" * 70)
    print("GENERATING VISUALIZATION CHARTS")
    print("=" * 70)

    print("\n📊 Creating strategy comparison charts...")
    plot_top_strategies()

    print("\n📊 Creating timeframe analysis...")
    plot_timeframe_analysis()

    print("\n📊 Creating risk analysis...")
    plot_risk_analysis()

    print("\n" + "=" * 70)
    print("✓ All charts generated!")
    print(f"Check {config.LOG_DIR} for PNG files")
    print("=" * 70)


if __name__ == "__main__":
    generate_all_charts()
