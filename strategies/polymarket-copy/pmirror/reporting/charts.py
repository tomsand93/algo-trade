"""
Chart generation for backtest visualization.

Uses matplotlib to generate equity curves, drawdown charts,
and other visualizations.
"""

from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Use non-interactive backend

import matplotlib.pyplot as plt
import numpy as np


def generate_equity_curve(
    timestamps: list[datetime],
    cash_values: list[float],
    output_path: str,
    title: str = "Equity Curve",
) -> None:
    """
    Generate an equity curve chart.

    Args:
        timestamps: List of timestamp values
        cash_values: List of portfolio values at each timestamp
        output_path: Path to save the chart image
        title: Chart title
    """
    if not timestamps or not cash_values:
        # Create empty chart with message
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, "No data available",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=12)
        ax.set_title(title)
        _save_chart(fig, output_path)
        return

    fig, ax = plt.subplots(figsize=(10, 6))

    # Plot equity curve
    ax.plot(timestamps, cash_values, linewidth=2, color="#2E86AB", label="Portfolio")

    # Format axes
    ax.set_xlabel("Time", fontsize=11)
    ax.set_ylabel("Portfolio Value ($)", fontsize=11)
    ax.set_title(title, fontsize=14, fontweight="bold")

    # Add grid
    ax.grid(True, alpha=0.3, linestyle="--")

    # Format x-axis dates
    fig.autofmt_xdate()

    # Add zero line for reference
    ax.axhline(y=cash_values[0], color="gray", linestyle="--",
               alpha=0.5, linewidth=1, label="Initial")

    # Format y-axis as currency
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    plt.tight_layout()
    _save_chart(fig, output_path)


def generate_drawdown_chart(
    timestamps: list[datetime],
    equity_values: list[float],
    output_path: str,
    title: str = "Drawdown Analysis",
) -> None:
    """
    Generate a drawdown chart showing underwater periods.

    Args:
        timestamps: List of timestamp values
        equity_values: List of portfolio values
        output_path: Path to save the chart image
        title: Chart title
    """
    if not timestamps or not equity_values:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, "No data available",
                ha="center", va="center", transform=ax.transAxes)
        ax.set_title(title)
        _save_chart(fig, output_path)
        return

    # Calculate drawdown
    equity_array = np.array(equity_values)
    peak = np.maximum.accumulate(equity_array)
    drawdown = (peak - equity_array) / peak * 100  # As percentage

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    # Plot equity curve
    ax1.plot(timestamps, equity_values, linewidth=2, color="#2E86AB")
    ax1.plot(timestamps, peak, linewidth=1, color="gray",
             linestyle="--", alpha=0.7, label="Peak")
    ax1.set_ylabel("Portfolio Value ($)", fontsize=11)
    ax1.set_title(title, fontsize=14, fontweight="bold")
    ax1.grid(True, alpha=0.3, linestyle="--")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax1.legend()

    # Plot drawdown
    ax2.fill_between(timestamps, drawdown, 0, color="#A23B72", alpha=0.3)
    ax2.plot(timestamps, drawdown, linewidth=2, color="#A23B72")
    ax2.set_xlabel("Time", fontsize=11)
    ax2.set_ylabel("Drawdown (%)", fontsize=11)
    ax2.grid(True, alpha=0.3, linestyle="--")
    ax2.axhline(y=0, color="black", linewidth=0.5)

    # Format x-axis dates
    fig.autofmt_xdate()

    plt.tight_layout()
    _save_chart(fig, output_path)


def generate_returns_distribution(
    returns: list[float],
    output_path: str,
    title: str = "Trade Returns Distribution",
) -> None:
    """
    Generate a histogram of trade returns.

    Args:
        returns: List of trade return values (as decimals)
        output_path: Path to save the chart image
        title: Chart title
    """
    if not returns:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, "No trade data available",
                ha="center", va="center", transform=ax.transAxes)
        ax.set_title(title)
        _save_chart(fig, output_path)
        return

    fig, ax = plt.subplots(figsize=(10, 6))

    # Convert to percentages
    returns_pct = [r * 100 for r in returns]

    # Plot histogram
    n, bins, patches = ax.hist(returns_pct, bins=20, color="#2E86AB",
                                 edgecolor="white", alpha=0.7)

    # Color negative returns red
    for i, patch in enumerate(patches):
        if bins[i] < 0:
            patch.set_facecolor("#A23B72")
            patch.set_alpha(0.7)

    # Add vertical line at 0
    ax.axvline(x=0, color="black", linewidth=1, linestyle="--")

    # Format
    ax.set_xlabel("Return (%)", fontsize=11)
    ax.set_ylabel("Frequency", fontsize=11)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.grid(True, alpha=0.3, linestyle="--", axis="y")

    plt.tight_layout()
    _save_chart(fig, output_path)


def _save_chart(fig, output_path: str) -> None:
    """
    Save chart to file and cleanup.

    Args:
        fig: Matplotlib figure
        output_path: Path to save the image
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fig.savefig(output_path, dpi=100, bbox_inches="tight", facecolor="white")
    plt.close(fig)
