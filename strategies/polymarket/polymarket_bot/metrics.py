"""Performance metrics for backtesting reports.

All functions use Python stdlib only (statistics, math).
No numpy/pandas — consistent with Phase 1 decision.

Annualization note: sqrt(252) convention is borrowed from equity markets.
For prediction markets this is an approximation; raw (non-annualized)
Sharpe can be recovered by dividing by sqrt(252).
"""
import math
import statistics


def win_rate(trade_pnls: list[float]) -> float:
    """Return win rate as percentage [0.0, 100.0].

    A trade is a winner if pnl > 0 (strictly positive, not breakeven).
    Returns 0.0 for empty trade list.
    """
    if not trade_pnls:
        return 0.0
    winners = sum(1 for p in trade_pnls if p > 0)
    return winners / len(trade_pnls) * 100.0


def sharpe_ratio(trade_pnls: list[float], risk_free_rate: float = 0.0) -> float | None:
    """Return annualized Sharpe ratio from per-trade PnL values.

    Returns None if < 2 trades or if standard deviation is zero.
    Annualization factor: sqrt(252) — equity market convention.
    """
    if len(trade_pnls) < 2:
        return None
    mean = statistics.mean(trade_pnls)
    std = statistics.stdev(trade_pnls)
    if std == 0.0:
        return None
    return (mean - risk_free_rate) / std * math.sqrt(252)


def sortino_ratio(trade_pnls: list[float], risk_free_rate: float = 0.0) -> float | None:
    """Return annualized Sortino ratio using downside standard deviation only.

    Returns None if < 2 trades, or if fewer than 2 losing trades (no downside std).
    Downside = trades with pnl < 0 (losses only, not breakeven).
    """
    if len(trade_pnls) < 2:
        return None
    mean = statistics.mean(trade_pnls)
    downside = [p for p in trade_pnls if p < 0]
    if len(downside) < 2:
        return None
    downside_std = statistics.stdev(downside)
    if downside_std == 0.0:
        return None
    return (mean - risk_free_rate) / downside_std * math.sqrt(252)


def max_drawdown(equity_curve: list[float]) -> float:
    """Return maximum drawdown as a negative percentage (e.g., -0.15 = -15%).

    equity_curve: list of portfolio values (not returns) in chronological order.
    Returns 0.0 for curves with fewer than 2 points or no drawdown.
    """
    if len(equity_curve) < 2:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        if peak > 0:
            dd = (value - peak) / peak
            if dd < max_dd:
                max_dd = dd
    return max_dd
