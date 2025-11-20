"""
Strategy Evaluator

Runs all strategies across all assets/timeframes/risk levels
Generates comprehensive reports
"""
import pandas as pd
from tqdm import tqdm
from database import OHLCVDatabase
from backtest_engine import BacktestEngine
from strategies import STRATEGIES
import config


class StrategyEvaluator:
    """Evaluate all strategy combinations"""

    def __init__(self):
        """Initialize evaluator"""
        self.db = OHLCVDatabase()
        self.engine = BacktestEngine()
        self.results = []

    def run_all(self):
        """Run backtests for all combinations"""
        print("=" * 70)
        print("STRATEGY EVALUATION")
        print("=" * 70)
        print(f"Strategies: {len(config.STRATEGIES)}")
        print(f"Assets: {len(config.CRYPTO_ASSETS)}")
        print(f"Timeframes: {len(config.CRYPTO_INTERVALS)}")
        print(f"Risk Levels: {len(config.RISK_LEVELS)}")

        # Database stats
        stats = self.db.get_stats()
        print(f"\nDatabase: {stats['total_candles']:,} candles, {stats['total_pairs']} pairs")
        print("=" * 70)

        # Calculate total iterations
        total = (
            len(config.STRATEGIES) *
            len(config.CRYPTO_ASSETS) *
            len(config.CRYPTO_INTERVALS) *
            len(config.RISK_LEVELS)
        )

        with tqdm(total=total, desc="Running backtests") as pbar:
            for strategy_name in config.STRATEGIES:
                if strategy_name not in STRATEGIES:
                    pbar.update(len(config.CRYPTO_ASSETS) * len(config.CRYPTO_INTERVALS) * len(config.RISK_LEVELS))
                    continue

                strategy_func = STRATEGIES[strategy_name]

                for asset in config.CRYPTO_ASSETS:
                    # Convert to CCXT format
                    if asset.endswith('USDT'):
                        symbol = f"{asset[:-4]}/USDT"
                    else:
                        symbol = asset

                    for timeframe in config.CRYPTO_INTERVALS:
                        # Load data from database
                        df = self.db.load_ohlcv(symbol, timeframe)

                        if df is None or df.empty or len(df) < config.MIN_CANDLES_REQUIRED:
                            pbar.update(len(config.RISK_LEVELS))
                            continue

                        for risk in config.RISK_LEVELS:
                            # Run backtest
                            result = self.engine.run(df, strategy_func, risk_per_trade=risk)

                            # Store results
                            self.results.append({
                                'strategy': strategy_name,
                                'asset': asset,
                                'timeframe': timeframe,
                                'risk': risk,
                                'initial_capital': config.INITIAL_CAPITAL,
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
                                'best_trade': result['metrics']['best_trade'],
                                'worst_trade': result['metrics']['worst_trade'],
                                'candles_analyzed': len(df),
                            })

                            pbar.update(1)

        print(f"\n✓ Completed {len(self.results)} backtests")

    def generate_reports(self):
        """Generate Excel, JSON, and text reports"""
        if not self.results:
            print("No results to report")
            return

        df = pd.DataFrame(self.results)

        # Excel report
        self._generate_excel_report(df)

        # JSON report
        self._generate_json_report(df)

        # Text summary
        self._generate_text_summary(df)

    def _generate_excel_report(self, df):
        """Generate Excel report with multiple sheets"""
        print("\nGenerating Excel report...")

        with pd.ExcelWriter(config.EXCEL_REPORT_PATH, engine='openpyxl') as writer:
            # All results
            df.to_excel(writer, sheet_name='All Results', index=False)

            # Top 50 by return
            top_return = df.nlargest(50, 'total_return_pct')
            top_return.to_excel(writer, sheet_name='Top 50 Return', index=False)

            # Top 50 by Sharpe
            top_sharpe = df.nlargest(50, 'sharpe_ratio')
            top_sharpe.to_excel(writer, sheet_name='Top 50 Sharpe', index=False)

            # Strategy summary
            strategy_summary = df.groupby('strategy').agg({
                'total_return_pct': ['mean', 'median', 'std', 'min', 'max'],
                'sharpe_ratio': ['mean', 'median'],
                'win_rate': ['mean', 'median'],
                'num_trades': 'sum',
                'profit_factor': 'mean'
            }).round(2)
            strategy_summary.to_excel(writer, sheet_name='Strategy Summary')

            # Asset summary
            asset_summary = df.groupby('asset').agg({
                'total_return_pct': ['mean', 'median', 'max'],
                'sharpe_ratio': 'mean',
                'win_rate': 'mean',
            }).round(2)
            asset_summary.to_excel(writer, sheet_name='Asset Summary')

            # Timeframe summary
            timeframe_summary = df.groupby('timeframe').agg({
                'total_return_pct': ['mean', 'median', 'max'],
                'sharpe_ratio': 'mean',
                'win_rate': 'mean',
            }).round(2)
            timeframe_summary.to_excel(writer, sheet_name='Timeframe Summary')

            # Risk summary
            risk_summary = df.groupby('risk').agg({
                'total_return_pct': ['mean', 'median', 'max'],
                'sharpe_ratio': 'mean',
                'win_rate': 'mean',
            }).round(2)
            risk_summary.to_excel(writer, sheet_name='Risk Summary')

        print(f"✓ Excel report: {config.EXCEL_REPORT_PATH}")

    def _generate_json_report(self, df):
        """Generate JSON report"""
        df.to_json(config.JSON_REPORT_PATH, orient='records', indent=2)
        print(f"✓ JSON report: {config.JSON_REPORT_PATH}")

    def _generate_text_summary(self, df):
        """Generate human-readable text summary"""
        with open(config.SUMMARY_REPORT_PATH, 'w') as f:
            f.write("=" * 70 + "\n")
            f.write("BACKTEST RESULTS SUMMARY\n")
            f.write("=" * 70 + "\n\n")

            f.write(f"Total Backtests: {len(df)}\n")
            f.write(f"Strategies: {df['strategy'].nunique()}\n")
            f.write(f"Assets: {df['asset'].nunique()}\n")
            f.write(f"Timeframes: {df['timeframe'].nunique()}\n\n")

            # Overall stats
            f.write("OVERALL STATISTICS\n")
            f.write("-" * 70 + "\n")
            f.write(f"Average Return: {df['total_return_pct'].mean():.2f}%\n")
            f.write(f"Median Return: {df['total_return_pct'].median():.2f}%\n")
            f.write(f"Best Return: {df['total_return_pct'].max():.2f}%\n")
            f.write(f"Worst Return: {df['total_return_pct'].min():.2f}%\n")
            f.write(f"Average Sharpe: {df['sharpe_ratio'].mean():.2f}\n")
            f.write(f"Average Win Rate: {df['win_rate'].mean():.1f}%\n\n")

            # Top 10
            f.write("TOP 10 PERFORMERS\n")
            f.write("-" * 70 + "\n")
            top_10 = df.nlargest(10, 'total_return_pct')

            for idx, row in enumerate(top_10.itertuples(), 1):
                f.write(f"\n#{idx}\n")
                f.write(f"  Strategy: {row.strategy}\n")
                f.write(f"  Asset: {row.asset}\n")
                f.write(f"  Timeframe: {row.timeframe}\n")
                f.write(f"  Risk: {row.risk*100:.0f}%\n")
                f.write(f"  Return: {row.total_return_pct:.2f}%\n")
                f.write(f"  Sharpe: {row.sharpe_ratio:.2f}\n")
                f.write(f"  Win Rate: {row.win_rate:.1f}%\n")
                f.write(f"  Max DD: {row.max_drawdown_pct:.2f}%\n")
                f.write(f"  Trades: {row.num_trades}\n")

            # Best by category
            f.write("\n\n" + "=" * 70 + "\n")
            f.write("BEST BY CATEGORY\n")
            f.write("=" * 70 + "\n\n")

            # Best strategy
            strategy_avg = df.groupby('strategy')['total_return_pct'].mean().sort_values(ascending=False)
            f.write(f"Best Strategy: {strategy_avg.index[0]} ({strategy_avg.iloc[0]:.2f}% avg)\n")

            # Best asset
            asset_avg = df.groupby('asset')['total_return_pct'].mean().sort_values(ascending=False)
            f.write(f"Best Asset: {asset_avg.index[0]} ({asset_avg.iloc[0]:.2f}% avg)\n")

            # Best timeframe
            tf_avg = df.groupby('timeframe')['total_return_pct'].mean().sort_values(ascending=False)
            f.write(f"Best Timeframe: {tf_avg.index[0]} ({tf_avg.iloc[0]:.2f}% avg)\n")

            # Best risk
            risk_avg = df.groupby('risk')['total_return_pct'].mean().sort_values(ascending=False)
            f.write(f"Best Risk Level: {risk_avg.index[0]*100:.0f}% ({risk_avg.iloc[0]:.2f}% avg)\n")

        print(f"✓ Text summary: {config.SUMMARY_REPORT_PATH}")

    def close(self):
        """Close database"""
        self.db.close()


def run_evaluation():
    """Main evaluation function"""
    evaluator = StrategyEvaluator()

    try:
        # Run backtests
        evaluator.run_all()

        # Generate reports
        evaluator.generate_reports()

        print("\n" + "=" * 70)
        print("EVALUATION COMPLETE!")
        print("=" * 70)
        print(f"\nReports saved to: {config.LOG_DIR}")

    finally:
        evaluator.close()


if __name__ == "__main__":
    run_evaluation()
