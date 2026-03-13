"""Report generation for backtest results."""

import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402


def write_outputs(results: dict, output_dir: Path) -> None:
    """Write backtest outputs to files.

    Args:
        results: Dictionary with 'equity', 'trades', 'metrics'
        output_dir: Directory to write outputs
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    # Write trades CSV
    if "trades" in results and len(results["trades"]) > 0:
        trades_path = output_dir / "trades.csv"
        results["trades"].to_csv(trades_path, index=False)
        print(f"Trades written to: {trades_path}")

    # Write equity CSV
    if "equity" in results:
        equity_path = output_dir / "equity.csv"
        results["equity"].to_csv(equity_path)
        print(f"Equity curve written to: {equity_path}")

    # Write summary JSON
    if "metrics" in results:
        # Convert numpy types for JSON serialization
        metrics_clean = {}
        for k, v in results["metrics"].items():
            if isinstance(v, (pd.Series, pd.DataFrame)):
                continue
            elif isinstance(v, (np.integer, np.floating)):
                metrics_clean[k] = float(v)
            else:
                metrics_clean[k] = v

        summary_path = output_dir / "summary.json"
        with open(summary_path, "w") as f:
            json.dump(metrics_clean, f, indent=2, default=float)
        print(f"Summary written to: {summary_path}")

    # Generate equity plot
    if "equity" in results:
        plot_equity(results["equity"], output_dir / "equity.png")


def plot_equity(equity_df: pd.DataFrame, output_path: Path) -> None:
    """Generate equity curve plot."""
    fig, ax = plt.subplots(figsize=(12, 6))

    ax.plot(equity_df.index, equity_df["equity"], linewidth=2, label="Equity")

    # Fill under curve
    ax.fill_between(
        equity_df.index,
        equity_df["equity"],
        equity_df["equity"].min(),
        alpha=0.3,
    )

    # Formatting
    ax.set_title("Equity Curve", fontsize=14, fontweight="bold")
    ax.set_xlabel("Time", fontsize=12)
    ax.set_ylabel("Equity ($)", fontsize=12)
    ax.grid(True, alpha=0.3)
    ax.legend()

    # Rotate x labels if needed
    fig.autofmt_xdate()

    plt.tight_layout()
    plt.savefig(output_path, dpi=100)
    plt.close()
    print(f"Equity plot saved to: {output_path}")
