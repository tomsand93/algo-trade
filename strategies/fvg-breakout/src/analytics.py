"""
FVG Breakout Strategy - Performance Analytics
==============================================
Comprehensive analysis and visualization of backtest results.
"""

from dataclasses import dataclass
from typing import Dict
import pandas as pd
import numpy as np
import json


@dataclass
class PerformanceReport:
    """Serialized performance report"""
    summary: Dict
    trade_breakdown: Dict
    monthly_analysis: Dict
    symbol_analysis: Dict


class PerformanceAnalyzer:
    """
    Analyzes backtest results and generates detailed reports.
    """

    def __init__(self, result: "BacktestResult"):  # noqa: F821
        self.result = result
        self.trades_df = self._trades_to_dataframe()

    def _trades_to_dataframe(self) -> pd.DataFrame:
        """Convert trades list to DataFrame for analysis."""
        if not self.result.trades:
            return pd.DataFrame()

        data = {
            "date": [t.date for t in self.result.trades],
            "symbol": [t.symbol for t in self.result.trades],
            "direction": [t.direction for t in self.result.trades],
            "entry_price": [t.entry_price for t in self.result.trades],
            "exit_price": [t.exit_price for t in self.result.trades],
            "pnl": [t.pnl for t in self.result.trades],
            "pnl_pct": [t.pnl_pct for t in self.result.trades],
            "r_multiple": [t.r_multiple for t in self.result.trades],
            "outcome": [t.outcome for t in self.result.trades],
            "exit_reason": [t.exit_reason for t in self.result.trades],
            "bars_held": [t.bars_held for t in self.result.trades]
        }
        return pd.DataFrame(data)

    def generate_summary(self) -> Dict:
        """Generate summary statistics."""
        r = self.result

        return {
            "Initial Capital": f"${self.result.initial_capital:,.2f}",
            "Final Equity": f"${r.equity_curve[-1]:,.2f}" if r.equity_curve else "N/A",
            "Total PnL": f"${r.total_pnl:,.2f}",
            "Total PnL %": f"{r.total_pnl_pct:.2f}%",
            "Total Trades": r.total_trades,
            "Winning Trades": r.winning_trades,
            "Losing Trades": r.losing_trades,
            "Win Rate": f"{r.win_rate:.2f}%",
            "Avg Win": f"${r.avg_win:.2f}",
            "Avg Loss": f"${r.avg_loss:.2f}",
            "Largest Win": f"${r.largest_win:.2f}",
            "Largest Loss": f"${r.largest_loss:.2f}",
            "Avg R Multiple": f"{r.avg_r_multiple:.2f}R",
            "Expectancy": f"${r.expectancy:.2f}",
            "Max Drawdown": f"${r.max_drawdown:,.2f}",
            "Max Drawdown %": f"{r.max_drawdown_pct:.2f}%",
            "Sharpe Ratio": f"{r.sharpe_ratio:.2f}"
        }

    def analyze_by_direction(self) -> Dict:
        """Analyze performance by trade direction."""
        if self.trades_df.empty:
            return {}

        result = {}

        for direction in ["long", "short"]:
            direction_trades = self.trades_df[self.trades_df["direction"] == direction]

            if direction_trades.empty:
                result[direction] = {"count": 0}
                continue

            wins = direction_trades[direction_trades["outcome"] == "WIN"]
            losses = direction_trades[direction_trades["outcome"] == "LOSS"]

            result[direction] = {
                "count": len(direction_trades),
                "wins": len(wins),
                "losses": len(losses),
                "win_rate": (len(wins) / len(direction_trades) * 100) if len(direction_trades) > 0 else 0,
                "total_pnl": direction_trades["pnl"].sum(),
                "avg_pnl": direction_trades["pnl"].mean(),
                "avg_r_multiple": direction_trades["r_multiple"].mean()
            }

        return result

    def analyze_by_symbol(self) -> Dict:
        """Analyze performance by symbol."""
        if self.trades_df.empty:
            return {}

        result = {}

        for symbol in self.trades_df["symbol"].unique():
            symbol_trades = self.trades_df[self.trades_df["symbol"] == symbol]

            wins = symbol_trades[symbol_trades["outcome"] == "WIN"]

            result[symbol] = {
                "total_trades": len(symbol_trades),
                "wins": len(wins),
                "win_rate": (len(wins) / len(symbol_trades) * 100) if len(symbol_trades) > 0 else 0,
                "total_pnl": symbol_trades["pnl"].sum(),
                "avg_pnl": symbol_trades["pnl"].mean(),
                "avg_r_multiple": symbol_trades["r_multiple"].mean()
            }

        return result

    def analyze_by_month(self) -> Dict:
        """Analyze performance by month."""
        if self.trades_df.empty:
            return {}

        df = self.trades_df.copy()
        df["month"] = pd.to_datetime(df["date"]).dt.to_period("M")

        result = {}

        for month in sorted(df["month"].unique()):
            month_trades = df[df["month"] == month]

            wins = month_trades[month_trades["outcome"] == "WIN"]
            losses = month_trades[month_trades["outcome"] == "LOSS"]

            result[str(month)] = {
                "trades": len(month_trades),
                "wins": len(wins),
                "losses": len(losses),
                "win_rate": (len(wins) / len(month_trades) * 100) if len(month_trades) > 0 else 0,
                "pnl": month_trades["pnl"].sum(),
                "avg_r_multiple": month_trades["r_multiple"].mean()
            }

        return result

    def analyze_exit_reasons(self) -> Dict:
        """Analyze exit reasons."""
        if self.trades_df.empty:
            return {}

        result = {}

        for reason in ["TAKE_PROFIT", "STOP_LOSS", "BREAK_EVEN", "EOD"]:
            reason_trades = self.trades_df[self.trades_df["exit_reason"] == reason]

            if reason_trades.empty:
                continue

            result[reason] = {
                "count": len(reason_trades),
                "pct_of_total": (len(reason_trades) / len(self.trades_df) * 100),
                "avg_pnl": reason_trades["pnl"].mean()
            }

        return result

    def analyze_holding_time(self) -> Dict:
        """Analyze trade holding time."""
        if self.trades_df.empty:
            return {}

        bars = self.trades_df["bars_held"]

        return {
            "avg_bars": int(bars.mean()),
            "median_bars": int(bars.median()),
            "min_bars": int(bars.min()),
            "max_bars": int(bars.max())
        }

    def calculate_streaks(self) -> Dict:
        """Calculate winning/losing streaks."""
        if self.trades_df.empty:
            return {}

        outcomes = [1 if t.outcome == "WIN" else -1 for t in self.result.trades]

        current_streak = 0
        max_win_streak = 0
        max_lose_streak = 0

        for o in outcomes:
            if o > 0:
                current_streak = current_streak + 1 if current_streak > 0 else 1
                max_win_streak = max(max_win_streak, current_streak)
            else:
                current_streak = current_streak - 1 if current_streak < 0 else -1
                max_lose_streak = max(max_lose_streak, abs(current_streak))

        return {
            "max_win_streak": max_win_streak,
            "max_lose_streak": max_lose_streak
        }

    def generate_full_report(self) -> PerformanceReport:
        """Generate comprehensive performance report."""
        return PerformanceReport(
            summary=self.generate_summary(),
            trade_breakdown={
                "by_direction": self.analyze_by_direction(),
                "by_symbol": self.analyze_by_symbol(),
                "by_month": self.analyze_by_month(),
                "exit_reasons": self.analyze_exit_reasons(),
                "holding_time": self.analyze_holding_time(),
                "streaks": self.calculate_streaks()
            },
            monthly_analysis=self.analyze_by_month(),
            symbol_analysis=self.analyze_by_symbol()
        )

    def print_report(self) -> None:
        """Print formatted report to console."""
        report = self.generate_full_report()

        print("=" * 60)
        print("FVG BREAKOUT STRATEGY - BACKTEST REPORT")
        print("=" * 60)
        print()

        print("[SUMMARY]")
        print("-" * 40)
        for key, value in report.summary.items():
            print(f"{key:20s}: {value}")
        print()

        print("[BREAKDOWN BY DIRECTION]")
        print("-" * 40)
        if not report.trade_breakdown["by_direction"]:
            print("No trades generated.")
            print()
            print("=" * 60)
            return

        for direction, stats in report.trade_breakdown["by_direction"].items():
            print(f"\n{direction.upper()}:")
            if stats.get("count", 0) > 0:
                print(f"  Trades:     {stats['count']}")
                print(f"  Win Rate:   {stats['win_rate']:.2f}%")
                print(f"  Total PnL:  ${stats['total_pnl']:.2f}")
                print(f"  Avg R Mult: {stats['avg_r_multiple']:.2f}R")
            else:
                print("  No trades")
        print()

        print("[BREAKDOWN BY SYMBOL]")
        print("-" * 40)
        for symbol, stats in report.symbol_analysis.items():
            print(f"\n{symbol}:")
            print(f"  Trades:    {stats['total_trades']}")
            print(f"  Win Rate:  {stats['win_rate']:.2f}%")
            print(f"  Total PnL: ${stats['total_pnl']:.2f}")
        print()

        print("[HOLDING TIME]")
        print("-" * 40)
        ht = report.trade_breakdown["holding_time"]
        print(f"Average: {ht['avg_bars']} bars")
        print(f"Median:  {ht['median_bars']} bars")
        print(f"Range:   {ht['min_bars']} - {ht['max_bars']} bars")
        print()

        print("[STREAKS]")
        print("-" * 40)
        streaks = report.trade_breakdown["streaks"]
        print(f"Max Win Streak:  {streaks['max_win_streak']}")
        print(f"Max Lose Streak: {streaks['max_lose_streak']}")
        print()

        print("=" * 60)

    def save_trades_csv(self, filepath: str) -> None:
        """Save individual trades to CSV."""
        if self.trades_df.empty:
            print("No trades to save.")
            return

        self.trades_df.to_csv(filepath, index=False)
        print(f"Trades saved to {filepath}")

    def save_report_json(self, filepath: str) -> None:
        """Save report to JSON."""
        report = self.generate_full_report()

        # Convert to serializable format
        def convert_types(obj):
            if isinstance(obj, pd.Timestamp):
                return str(obj)
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return obj

        with open(filepath, "w") as f:
            json.dump(report.__dict__, f, default=convert_types, indent=2)

        print(f"Report saved to {filepath}")


def plot_equity_curve(result: "BacktestResult", save_path: str = None) -> None:  # noqa: F821
    """
    Plot equity curve.

    Requires matplotlib.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed. Run: pip install matplotlib")
        return

    if not result.equity_curve:
        print("No equity data to plot.")
        return

    plt.figure(figsize=(12, 6))

    # Plot equity curve
    plt.plot(result.equity_curve, linewidth=2, color="#2E86AB", label="Equity")

    # Plot initial capital line
    plt.axhline(
        y=result.initial_capital,
        color="#A23B72",
        linestyle="--",
        alpha=0.5,
        label="Initial Capital"
    )

    # Highlight drawdown periods
    equity = np.array(result.equity_curve)
    running_max = np.maximum.accumulate(equity)

    plt.fill_between(
        range(len(equity)),
        equity,
        running_max,
        where=(equity < running_max),
        color="#F25F5C",
        alpha=0.3,
        label="Drawdown"
    )

    plt.title("FVG Breakout Strategy - Equity Curve", fontsize=14, fontweight="bold")
    plt.xlabel("Trade Number")
    plt.ylabel("Equity ($)")
    plt.legend(loc="best")
    plt.grid(True, alpha=0.3)

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Equity curve saved to {save_path}")
    else:
        plt.show()

    plt.close()


def plot_r_multiple_distribution(result: "BacktestResult", save_path: str = None) -> None:  # noqa: F821
    """
    Plot R multiple distribution.

    Requires matplotlib.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed. Run: pip install matplotlib")
        return

    if not result.trades:
        print("No trades to plot.")
        return

    r_multiples = [t.r_multiple for t in result.trades]

    plt.figure(figsize=(10, 6))

    # Histogram
    n, bins, patches = plt.hist(r_multiples, bins=20, edgecolor="black", alpha=0.7)

    # Color bars: green for positive, red for negative
    for i, patch in enumerate(patches):
        if bins[i] >= 0:
            patch.set_facecolor("#7FB069")
        else:
            patch.set_facecolor("#D72638")

    plt.axvline(x=0, color="black", linestyle="-", linewidth=1)
    plt.axvline(x=np.mean(r_multiples), color="blue", linestyle="--", linewidth=2, label=f"Mean: {np.mean(r_multiples):.2f}R")

    plt.title("R Multiple Distribution", fontsize=14, fontweight="bold")
    plt.xlabel("R Multiple")
    plt.ylabel("Frequency")
    plt.legend(loc="best")
    plt.grid(True, alpha=0.3)

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"R multiple plot saved to {save_path}")
    else:
        plt.show()

    plt.close()
