"""
Plotting and visualization for backtest results.

Creates:
- Equity curves
- Drawdown charts
- Trade distribution
- Parameter sweep heatmaps
"""
import logging
from datetime import date
from decimal import Decimal
from typing import List, Tuple, Dict, Any, Optional
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# Set style
plt.style.use("seaborn-v0_8-darkgrid")


def plot_equity_curve(
    equity_curve: List[Tuple[date, Decimal]],
    benchmark_curve: Optional[List[Tuple[date, float]]] = None,
    title: str = "Equity Curve",
    output_path: Optional[str] = None,
) -> None:
    """
    Plot equity curve with optional benchmark.

    Args:
        equity_curve: List of (date, equity) tuples
        benchmark_curve: Optional benchmark (date, value) tuples
        title: Chart title
        output_path: Path to save figure
    """
    fig, ax = plt.subplots(figsize=(12, 6))

    dates = [e[0] for e in equity_curve]
    values = [float(e[1]) for e in equity_curve]

    # Normalize to starting value
    initial = values[0]
    normalized_values = [v / initial for v in values]

    ax.plot(dates, normalized_values, label="Strategy", linewidth=2)

    # Add benchmark if provided
    if benchmark_curve:
        bm_dates = [e[0] for e in benchmark_curve]
        bm_values = [e[1] for e in benchmark_curve]
        bm_initial = bm_values[0]
        bm_normalized = [v / bm_initial for v in bm_values]

        ax.plot(bm_dates, bm_normalized, label="Benchmark", linewidth=2, alpha=0.7)

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Normalized Value", fontsize=12)
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)

    # Format x-axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

    plt.tight_layout()

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info(f"Equity curve saved to {output_path}")
    else:
        plt.show()

    plt.close()


def plot_drawdown(
    equity_curve: List[Tuple[date, Decimal]],
    title: str = "Drawdown",
    output_path: Optional[str] = None,
) -> None:
    """
    Plot drawdown chart.

    Args:
        equity_curve: List of (date, equity) tuples
        title: Chart title
        output_path: Path to save figure
    """
    fig, ax = plt.subplots(figsize=(12, 6))

    dates = [e[0] for e in equity_curve]
    values = [float(e[1]) for e in equity_curve]

    # Calculate drawdown
    equity_array = np.array(values)
    peaks = np.maximum.accumulate(equity_array)
    drawdowns = (equity_array - peaks) / peaks

    ax.fill_between(dates, drawdowns * 100, 0, alpha=0.3, color="red")
    ax.plot(dates, drawdowns * 100, color="red", linewidth=1.5)

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Drawdown (%)", fontsize=12)
    ax.grid(True, alpha=0.3)

    # Format x-axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

    plt.tight_layout()

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info(f"Drawdown chart saved to {output_path}")
    else:
        plt.show()

    plt.close()


def plot_trade_distribution(
    trades: List[Dict[str, Any]],
    title: str = "Trade PnL Distribution",
    output_path: Optional[str] = None,
) -> None:
    """
    Plot histogram of trade PnL.

    Args:
        trades: List of trade result dictionaries
        title: Chart title
        output_path: Path to save figure
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    pnls = [float(t.get("net_pnl", 0)) for t in trades]

    # Histogram
    ax1.hist(pnls, bins=30, edgecolor="black", alpha=0.7)
    ax1.axvline(x=0, color="red", linestyle="--", linewidth=2)
    ax1.set_title("Trade PnL Distribution", fontsize=12, fontweight="bold")
    ax1.set_xlabel("PnL ($)", fontsize=11)
    ax1.set_ylabel("Frequency", fontsize=11)
    ax1.grid(True, alpha=0.3)

    # Cumulative returns
    cumulative = np.cumsum(pnls)
    ax2.plot(range(len(cumulative)), cumulative, linewidth=2)
    ax2.axhline(y=0, color="black", linestyle="-", linewidth=0.5)
    ax2.set_title("Cumulative PnL", fontsize=12, fontweight="bold")
    ax2.set_xlabel("Trade Number", fontsize=11)
    ax2.set_ylabel("Cumulative PnL ($)", fontsize=11)
    ax2.grid(True, alpha=0.3)

    plt.suptitle(title, fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info(f"Trade distribution saved to {output_path}")
    else:
        plt.show()

    plt.close()


def plot_parameter_heatmap(
    sweep_results: pd.DataFrame,
    param_x: str,
    param_y: str,
    value_col: str = "cagr",
    title: Optional[str] = None,
    output_path: Optional[str] = None,
) -> None:
    """
    Plot heatmap of parameter sweep results.

    Args:
        sweep_results: DataFrame from parameter sweep
        param_x: Parameter for x-axis
        param_y: Parameter for y-axis
        value_col: Column to use for color values
        title: Chart title
        output_path: Path to save figure
    """
    # Pivot the data
    pivot_table = sweep_results.pivot_table(
        values=value_col,
        index=param_y,
        columns=param_x,
        aggfunc="mean"
    )

    fig, ax = plt.subplots(figsize=(10, 8))

    im = ax.imshow(pivot_table.values, cmap="RdYlGn", aspect="auto")

    # Set ticks
    ax.set_xticks(np.arange(len(pivot_table.columns)))
    ax.set_yticks(np.arange(len(pivot_table.index)))
    ax.set_xticklabels(pivot_table.columns)
    ax.set_yticklabels(pivot_table.index)

    # Add colorbar
    cbar = ax.figure.colorbar(im, ax=ax)
    cbar.set_label(value_col, rotation=270, labelpad=15)

    # Add text annotations
    for i in range(len(pivot_table.index)):
        for j in range(len(pivot_table.columns)):
            value = pivot_table.values[i, j]
            text_color = "white" if abs(value) > abs(pivot_table.values.max()) / 2 else "black"
            ax.text(j, i, f"{value:.2%}", ha="center", va="center", color=text_color, fontsize=9)

    ax.set_xlabel(param_x, fontsize=12)
    ax.set_ylabel(param_y, fontsize=12)

    if title:
        ax.set_title(title, fontsize=14, fontweight="bold")
    else:
        ax.set_title(f"{value_col} by {param_x} and {param_y}", fontsize=14, fontweight="bold")

    plt.tight_layout()

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info(f"Parameter heatmap saved to {output_path}")
    else:
        plt.show()

    plt.close()


def create_full_report(
    results: Dict[str, Any],
    trades: List[Dict[str, Any]],
    output_dir: str,
) -> None:
    """
    Create a full visual report.

    Args:
        results: Backtest results dictionary
        trades: List of trade results
        output_dir: Directory to save plots
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Equity curve
    equity_curve = [(date.fromisoformat(d), Decimal(v)) for d, v in results.get("equity_curve", [])]
    if equity_curve:
        plot_equity_curve(
            equity_curve,
            title="Insider Buy Strategy - Equity Curve",
            output_path=str(output_path / "equity_curve.png")
        )

        # Drawdown
        plot_drawdown(
            equity_curve,
            title="Insider Buy Strategy - Drawdown",
            output_path=str(output_path / "drawdown.png")
        )

    # Trade distribution
    if trades:
        # Convert trade results to dict format for plotting
        trade_dicts = [
            {
                "net_pnl": str(t.net_pnl),
                "hold_bars": t.hold_bars,
                "exit_reason": t.exit_reason,
            }
            for t in trades
        ]
        plot_trade_distribution(
            trade_dicts,
            title="Insider Buy Strategy - Trade Distribution",
            output_path=str(output_path / "trade_distribution.png")
        )

    logger.info(f"Full report saved to {output_dir}")


def plot_monthly_returns(
    equity_curve: List[Tuple[date, Decimal]],
    title: str = "Monthly Returns",
    output_path: Optional[str] = None,
) -> None:
    """
    Plot monthly return heatmap.

    Args:
        equity_curve: List of (date, equity) tuples
        title: Chart title
        output_path: Path to save figure
    """
    # Convert to DataFrame
    df = pd.DataFrame([
        {"date": d, "equity": float(v)}
        for d, v in equity_curve
    ])
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)

    # Calculate monthly returns
    monthly = df.resample("M").last()
    monthly_returns = monthly["equity"].pct_change()

    # Create year/month columns
    monthly_returns_df = monthly_returns.to_frame("returns")
    monthly_returns_df["year"] = monthly_returns_df.index.year
    monthly_returns_df["month"] = monthly_returns_df.index.month

    # Pivot
    pivot = monthly_returns_df.pivot(index="year", columns="month", values="returns")
    pivot.columns = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    fig, ax = plt.subplots(figsize=(12, 8))

    im = ax.imshow(pivot.values * 100, cmap="RdYlGn", aspect="auto")

    ax.set_xticks(np.arange(len(pivot.columns)))
    ax.set_yticks(np.arange(len(pivot.index)))
    ax.set_xticklabels(pivot.columns)
    ax.set_yticklabels(pivot.index)

    # Add text annotations
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            value = pivot.values[i, j]
            if not np.isnan(value):
                text_color = "white" if abs(value) > 0.02 else "black"
                ax.text(j, i, f"{value*100:.1f}%", ha="center", va="center",
                        color=text_color, fontsize=9)

    ax.figure.colorbar(im, ax=ax, label="Return (%)")
    ax.set_title(title, fontsize=14, fontweight="bold")

    plt.tight_layout()

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info(f"Monthly returns saved to {output_path}")
    else:
        plt.show()

    plt.close()
