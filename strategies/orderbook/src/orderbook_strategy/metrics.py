"""Performance metrics computation."""

from typing import Dict

import numpy as np
import pandas as pd


def compute_metrics(equity_curve: pd.DataFrame, trades: pd.DataFrame) -> Dict:
    """Compute comprehensive performance metrics.

    Args:
        equity_curve: DataFrame with 'equity' column and datetime index
        trades: DataFrame with trade records including 'pnl' column

    Returns:
        Dictionary of metrics
    """
    if len(equity_curve) < 2:
        return {}

    # Returns
    equity_curve["returns"] = equity_curve["equity"].pct_change()
    returns = equity_curve["returns"].dropna()

    initial_equity = equity_curve["equity"].iloc[0]
    final_equity = equity_curve["equity"].iloc[-1]

    # Basic metrics
    total_return = (final_equity / initial_equity) - 1

    # Annualization (compute from actual time span)
    time_span = (equity_curve.index[-1] - equity_curve.index[0]).total_seconds()
    if time_span > 0:
        seconds_per_year = 365.25 * 24 * 3600
        ann_factor = seconds_per_year / time_span
        ann_return = (1 + total_return) ** ann_factor - 1
        ann_vol = returns.std() * np.sqrt(ann_factor)
    else:
        ann_factor = 252  # Default to daily
        ann_return = total_return
        ann_vol = returns.std() * np.sqrt(ann_factor)

    # Risk-adjusted returns
    sharpe = ann_return / ann_vol if ann_vol > 0 else 0

    # Sortino (downside deviation)
    downside_returns = returns[returns < 0]
    downside_vol = downside_returns.std() * np.sqrt(ann_factor) if len(downside_returns) > 0 else 0
    sortino = ann_return / downside_vol if downside_vol > 0 else 0

    # Drawdown
    rolling_max = equity_curve["equity"].cummax()
    drawdown = (equity_curve["equity"] - rolling_max) / rolling_max
    max_drawdown = drawdown.min()

    # Trade metrics
    if len(trades) > 0 and "pnl" in trades.columns:
        wins = trades[trades["pnl"] > 0]
        losses = trades[trades["pnl"] < 0]

        win_rate = len(wins) / len(trades) if len(trades) > 0 else 0

        avg_win = wins["pnl"].mean() if len(wins) > 0 else 0
        avg_loss = losses["pnl"].mean() if len(losses) > 0 else 0

        gross_profit = wins["pnl"].sum() if len(wins) > 0 else 0
        gross_loss = abs(losses["pnl"].sum()) if len(losses) > 0 else 0

        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0)

        avg_trade = trades["pnl"].mean()
    else:
        win_rate = 0
        avg_win = 0
        avg_loss = 0
        profit_factor = 0
        avg_trade = 0

    return {
        "total_return": total_return,
        "annual_return": ann_return,
        "annual_volatility": ann_vol,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "avg_trade": avg_trade,
        "num_trades": len(trades),
        "final_equity": final_equity,
    }


def format_metrics(metrics: Dict) -> str:
    """Format metrics for display."""
    lines = ["=" * 50, "BACKTEST RESULTS", "=" * 50]

    for key, value in metrics.items():
        if isinstance(value, float):
            if "return" in key or "drawdown" in key:
                lines.append(f"{key:20s}: {value:>+10.2%}")
            elif "rate" in key:
                lines.append(f"{key:20s}: {value:>10.1%}")
            elif "ratio" in key:
                lines.append(f"{key:20s}: {value:>10.3f}")
            else:
                lines.append(f"{key:20s}: {value:>10.2f}")
        else:
            lines.append(f"{key:20s}: {value}")

    lines.append("=" * 50)
    return "\n".join(lines)
