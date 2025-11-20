"""
Evaluator - Runs all strategies on all assets and timeframes
Generates comprehensive comparison reports
"""
import pandas as pd
import numpy as np
from tqdm import tqdm
from pathlib import Path
import json
from datetime import datetime

import config
from backtester import Backtester
from strategies_advanced import STRATEGIES
from data_fetcher import BinanceDataFetcher


class StrategyEvaluator:
    """Evaluate all strategies across assets and timeframes"""

    def __init__(self, initial_capital=10000, commission=0.001):
        """
        Initialize evaluator

        Args:
            initial_capital: Starting capital for each backtest
            commission: Trading commission (0.001 = 0.1%)
        """
        self.initial_capital = initial_capital
        self.commission = commission
        self.backtester = Backtester(initial_capital, commission)
        self.fetcher = BinanceDataFetcher(use_testnet=False)
        self.results = []

    def evaluate_all(self):
        """Run backtests for all combinations of strategy/asset/timeframe/risk"""

        print("=" * 70)
        print("BACKTESTING EVALUATION")
        print("=" * 70)
        print(f"Initial Capital: ${self.initial_capital}")
        print(f"Commission: {self.commission*100}%")
        print(f"Strategies: {list(STRATEGIES.keys())}")
        print(f"Assets: {config.CRYPTO_ASSETS}")
        print(f"Risk Levels: {config.RISK_LEVELS}")
        print("=" * 70)

        # Calculate total iterations
        total_iterations = (
            len(STRATEGIES) *
            len(config.CRYPTO_ASSETS) *
            len(config.CRYPTO_INTERVALS) *
            len(config.RISK_LEVELS)
        )

        with tqdm(total=total_iterations, desc="Running backtests") as pbar:
            for strategy_name, strategy_func in STRATEGIES.items():
                for asset in config.CRYPTO_ASSETS:
                    # Convert to CCXT format
                    if asset.endswith('USDT'):
                        symbol = f"{asset[:-4]}/USDT"
                    else:
                        symbol = asset

                    for timeframe in config.CRYPTO_INTERVALS:
                        # Load data
                        df = self.fetcher.load_from_csv(symbol, timeframe)

                        if df is None or df.empty or len(df) < config.MIN_CANDLES_REQUIRED:
                            pbar.update(len(config.RISK_LEVELS))
                            continue

                        for risk in config.RISK_LEVELS:
                            # Run backtest
                            result = self.backtester.run(
                                df,
                                strategy_func,
                                risk_per_trade=risk
                            )

                            # Store results
                            self.results.append({
                                'strategy': strategy_name,
                                'asset': asset,
                                'timeframe': timeframe,
                                'risk': risk,
                                'initial_capital': self.initial_capital,
                                'final_equity': result['final_equity'],
                                'total_return': result['metrics']['total_return'],
                                'total_return_pct': result['metrics']['total_return_pct'],
                                'num_trades': result['metrics']['num_trades'],
                                'win_rate': result['metrics']['win_rate'],
                                'profit_factor': result['metrics']['profit_factor'],
                                'max_drawdown_pct': result['metrics']['max_drawdown_pct'],
                                'sharpe_ratio': result['metrics']['sharpe_ratio'],
                                'sortino_ratio': result['metrics']['sortino_ratio'],
                                'avg_win': result['metrics']['avg_win'],
                                'avg_loss': result['metrics']['avg_loss'],
                                'total_commission': result['metrics']['total_commission'],
                                'candles_analyzed': len(df),
                            })

                            pbar.update(1)

        print(f"\n✓ Completed {len(self.results)} backtests")
        return self.results

    def generate_reports(self):
        """Generate comprehensive reports and save to files"""

        if not self.results:
            print("No results to report")
            return

        # Create DataFrame
        df = pd.DataFrame(self.results)

        # Save full results
        config.LOG_DIR.mkdir(exist_ok=True)
        excel_path = config.LOG_DIR / "backtest_results.xlsx"

        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            # Full results
            df.to_excel(writer, sheet_name='All Results', index=False)

            # Top performers by return
            top_by_return = df.nlargest(50, 'total_return_pct')
            top_by_return.to_excel(writer, sheet_name='Top 50 by Return', index=False)

            # Top by Sharpe ratio
            top_by_sharpe = df.nlargest(50, 'sharpe_ratio')
            top_by_sharpe.to_excel(writer, sheet_name='Top 50 by Sharpe', index=False)

            # Summary by strategy
            strategy_summary = df.groupby('strategy').agg({
                'total_return_pct': ['mean', 'median', 'std', 'min', 'max'],
                'sharpe_ratio': ['mean', 'median'],
                'win_rate': ['mean', 'median'],
                'num_trades': 'sum',
                'profit_factor': 'mean'
            }).round(2)
            strategy_summary.to_excel(writer, sheet_name='Strategy Summary')

            # Summary by asset
            asset_summary = df.groupby('asset').agg({
                'total_return_pct': ['mean', 'median', 'std', 'min', 'max'],
                'sharpe_ratio': ['mean', 'median'],
                'win_rate': ['mean', 'median'],
            }).round(2)
            asset_summary.to_excel(writer, sheet_name='Asset Summary')

            # Summary by timeframe
            timeframe_summary = df.groupby('timeframe').agg({
                'total_return_pct': ['mean', 'median', 'std', 'min', 'max'],
                'sharpe_ratio': ['mean', 'median'],
                'win_rate': ['mean', 'median'],
            }).round(2)
            timeframe_summary.to_excel(writer, sheet_name='Timeframe Summary')

            # Summary by risk level
            risk_summary = df.groupby('risk').agg({
                'total_return_pct': ['mean', 'median', 'std', 'min', 'max'],
                'sharpe_ratio': ['mean', 'median'],
                'win_rate': ['mean', 'median'],
            }).round(2)
            risk_summary.to_excel(writer, sheet_name='Risk Summary')

        print(f"✓ Saved Excel report: {excel_path}")

        # Generate text summary
        self._generate_text_summary(df)

        # Generate JSON for programmatic access
        json_path = config.LOG_DIR / "backtest_results.json"
        df.to_json(json_path, orient='records', indent=2)
        print(f"✓ Saved JSON report: {json_path}")

    def _generate_text_summary(self, df):
        """Generate human-readable text summary"""

        summary_path = config.LOG_DIR / "summary.txt"

        with open(summary_path, 'w') as f:
            f.write("=" * 70 + "\n")
            f.write("BACKTEST RESULTS SUMMARY\n")
            f.write("=" * 70 + "\n\n")

            f.write(f"Total Backtests Run: {len(df)}\n")
            f.write(f"Strategies Tested: {df['strategy'].nunique()}\n")
            f.write(f"Assets Tested: {df['asset'].nunique()}\n")
            f.write(f"Timeframes Tested: {df['timeframe'].nunique()}\n\n")

            # Overall statistics
            f.write("OVERALL STATISTICS\n")
            f.write("-" * 70 + "\n")
            f.write(f"Average Return: {df['total_return_pct'].mean():.2f}%\n")
            f.write(f"Median Return: {df['total_return_pct'].median():.2f}%\n")
            f.write(f"Best Return: {df['total_return_pct'].max():.2f}%\n")
            f.write(f"Worst Return: {df['total_return_pct'].min():.2f}%\n")
            f.write(f"Average Sharpe Ratio: {df['sharpe_ratio'].mean():.2f}\n")
            f.write(f"Average Win Rate: {df['win_rate'].mean():.1f}%\n\n")

            # Top 10 performers
            f.write("TOP 10 PERFORMERS (by Total Return %)\n")
            f.write("-" * 70 + "\n")
            top_10 = df.nlargest(10, 'total_return_pct')

            for idx, row in top_10.iterrows():
                f.write(f"\n#{top_10.index.get_loc(idx) + 1}\n")
                f.write(f"  Strategy: {row['strategy']}\n")
                f.write(f"  Asset: {row['asset']}\n")
                f.write(f"  Timeframe: {row['timeframe']}\n")
                f.write(f"  Risk: {row['risk']*100:.0f}%\n")
                f.write(f"  Return: {row['total_return_pct']:.2f}%\n")
                f.write(f"  Sharpe Ratio: {row['sharpe_ratio']:.2f}\n")
                f.write(f"  Win Rate: {row['win_rate']:.1f}%\n")
                f.write(f"  Max Drawdown: {row['max_drawdown_pct']:.2f}%\n")
                f.write(f"  Trades: {row['num_trades']}\n")

            # Best strategy by average performance
            f.write("\n\n" + "=" * 70 + "\n")
            f.write("BEST STRATEGY (by Average Return)\n")
            f.write("=" * 70 + "\n")
            strategy_avg = df.groupby('strategy')['total_return_pct'].mean().sort_values(ascending=False)
            best_strategy = strategy_avg.index[0]
            best_strategy_return = strategy_avg.iloc[0]

            f.write(f"Strategy: {best_strategy}\n")
            f.write(f"Average Return: {best_strategy_return:.2f}%\n")

            # Get best configuration for this strategy
            best_config = df[df['strategy'] == best_strategy].nlargest(1, 'total_return_pct').iloc[0]
            f.write(f"Best Config: {best_config['asset']} @ {best_config['timeframe']} (Risk: {best_config['risk']*100:.0f}%)\n")
            f.write(f"Best Return: {best_config['total_return_pct']:.2f}%\n")

            # Best asset
            f.write("\n\n" + "=" * 70 + "\n")
            f.write("BEST ASSET (by Average Return)\n")
            f.write("=" * 70 + "\n")
            asset_avg = df.groupby('asset')['total_return_pct'].mean().sort_values(ascending=False)
            f.write(f"Asset: {asset_avg.index[0]}\n")
            f.write(f"Average Return: {asset_avg.iloc[0]:.2f}%\n")

            # Best timeframe
            f.write("\n\n" + "=" * 70 + "\n")
            f.write("BEST TIMEFRAME (by Average Return)\n")
            f.write("=" * 70 + "\n")
            timeframe_avg = df.groupby('timeframe')['total_return_pct'].mean().sort_values(ascending=False)
            f.write(f"Timeframe: {timeframe_avg.index[0]}\n")
            f.write(f"Average Return: {timeframe_avg.iloc[0]:.2f}%\n")

            # Best risk level
            f.write("\n\n" + "=" * 70 + "\n")
            f.write("BEST RISK LEVEL (by Average Return)\n")
            f.write("=" * 70 + "\n")
            risk_avg = df.groupby('risk')['total_return_pct'].mean().sort_values(ascending=False)
            f.write(f"Risk Level: {risk_avg.index[0]*100:.0f}%\n")
            f.write(f"Average Return: {risk_avg.iloc[0]:.2f}%\n")

        print(f"✓ Saved text summary: {summary_path}")


def run_evaluation():
    """Main function to run the evaluation"""
    evaluator = StrategyEvaluator(
        initial_capital=config.START_BALANCE,
        commission=0.001  # 0.1% Binance fee
    )

    # Run all backtests
    evaluator.evaluate_all()

    # Generate reports
    evaluator.generate_reports()

    print("\n" + "=" * 70)
    print("EVALUATION COMPLETE!")
    print("=" * 70)
    print(f"Check {config.LOG_DIR} for detailed reports")


if __name__ == "__main__":
    run_evaluation()
