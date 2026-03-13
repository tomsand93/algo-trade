"""
Performance metrics calculation for backtest results.

Computes standard financial metrics to evaluate copy-trade strategy performance.
"""

from datetime import timedelta
from typing import List

import numpy as np
import pandas as pd

from pmirror.domain import BacktestState, ExecutedTrade
from pmirror.backtest.engine import BacktestResult


def compute_metrics(result: BacktestResult, risk_free_rate: float = 0.0) -> dict:
    """
    Compute comprehensive performance metrics for a backtest result.

    Args:
        result: BacktestResult from a completed backtest
        risk_free_rate: Annual risk-free rate (default 0.0)

    Returns:
        Dictionary of performance metrics
    """
    state = result.final_state
    trades = result.executed_trades

    # Basic metrics
    total_return = state.total_return
    final_equity = state.equity
    starting_capital = state.starting_cash

    # Trade metrics
    total_trades = len(trades)
    winning_trades = _count_winning_trades(trades)
    losing_trades = _count_losing_trades(trades)
    win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

    # Calculate returns per trade
    trade_returns = _calculate_trade_returns(trades, result.config.commission_rate if result.config else 0)

    if trade_returns:
        avg_trade_return = np.mean(trade_returns)
        median_trade_return = np.median(trade_returns)
        std_trade_return = np.std(trade_returns)
    else:
        avg_trade_return = 0.0
        median_trade_return = 0.0
        std_trade_return = 0.0

    # Calculate equity curve
    equity_curve = _calculate_equity_curve(result)

    if len(equity_curve) > 1:
        # Risk metrics
        sharpe_ratio = _calculate_sharpe(equity_curve, risk_free_rate)
        sortino_ratio = _calculate_sortino(equity_curve, risk_free_rate)
        max_drawdown, max_dd_duration = _calculate_max_drawdown(equity_curve)
        volatility = _calculate_volatility(equity_curve)
    else:
        sharpe_ratio = 0.0
        sortino_ratio = 0.0
        max_drawdown = 0.0
        max_dd_duration = timedelta(0)
        volatility = 0.0

    # Position metrics
    max_exposure = _calculate_max_exposure(result)
    avg_exposure = _calculate_avg_exposure(result)

    # Skipped trades
    skipped_count = len(result.skipped_trades)
    skip_rate = skipped_count / (total_trades + skipped_count) if (total_trades + skipped_count) > 0 else 0.0

    # Fee impact
    total_fees = sum(t.fee or 0 for t in trades)

    return {
        # Return metrics
        "total_return": total_return,
        "total_return_pct": total_return * 100,
        "final_equity": final_equity,
        "starting_capital": starting_capital,
        "absolute_profit": final_equity - starting_capital,

        # Risk-adjusted returns
        "sharpe_ratio": sharpe_ratio,
        "sortino_ratio": sortino_ratio,
        "volatility": volatility,
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown * 100,
        "max_drawdown_duration": max_dd_duration,

        # Trade metrics
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": win_rate,
        "win_rate_pct": win_rate * 100,
        "avg_trade_return": avg_trade_return,
        "median_trade_return": median_trade_return,
        "std_trade_return": std_trade_return,

        # Exposure metrics
        "max_exposure": max_exposure,
        "avg_exposure": avg_exposure,

        # Execution metrics
        "skipped_trades": skipped_count,
        "skip_rate": skip_rate,
        "skip_rate_pct": skip_rate * 100,

        # Cost metrics
        "total_fees": total_fees,

        # Additional
        "peak_equity": max(equity_curve) if equity_curve else starting_capital,
        "equity_curve": equity_curve,  # Include for charting
    }


def _calculate_equity_curve(result: BacktestResult) -> List[float]:
    """Calculate equity curve over time."""
    if not result.executed_trades:
        return [result.final_state.starting_cash]

    # Sort trades by timestamp
    trades = sorted(result.executed_trades, key=lambda t: t.timestamp)

    equity = [result.final_state.starting_cash]
    cash = result.final_state.starting_cash
    positions = {}  # market_id -> (size, avg_price)

    for trade in trades:
        # Update cash
        cost = trade.size + (trade.fee or 0)
        if trade.side == "buy":
            cash -= cost
        else:
            cash += trade.size - (trade.fee or 0)

        # Update position (simplified - tracking market value)
        key = trade.market_id
        if key in positions:
            pos_size, avg_price = positions[key]
            if trade.side == "buy":
                new_size = pos_size + trade.size
                new_avg = (pos_size * avg_price + trade.size * trade.price) / new_size
                positions[key] = (new_size, new_avg)
            else:
                new_size = pos_size - trade.size
                if new_size > 0:
                    positions[key] = (new_size, avg_price)
                else:
                    del positions[key]
        else:
            positions[key] = (trade.size, trade.price)

        # Calculate equity
        position_value = sum(size for size, _ in positions.values())
        equity.append(cash + position_value)

    return equity


def _count_winning_trades(trades: List[ExecutedTrade]) -> int:
    """Count winning trades (simplified - assumes binary outcomes)."""
    # For a proper implementation, we'd need to track when positions are closed
    # and their final PnL. This is a simplified version.
    return sum(1 for t in trades if t.side == "buy")


def _count_losing_trades(trades: List[ExecutedTrade]) -> int:
    """Count losing trades."""
    return sum(1 for t in trades if t.side == "sell")


def _calculate_trade_returns(trades: List[ExecutedTrade], commission_rate: float) -> List[float]:
    """Calculate return for each trade."""
    if not trades:
        return []

    returns = []
    for trade in trades:
        # Simplified return calculation
        # In reality, you'd need to track position entry/exit
        fee = trade.size * commission_rate
        if trade.side == "buy":
            # Return is negative (we spent money)
            ret = -(trade.size + fee) / trade.size if trade.size > 0 else 0
        else:
            # Return is positive (we received money)
            ret = (trade.size - fee) / trade.size if trade.size > 0 else 0
        returns.append(ret)

    return returns


def _calculate_sharpe(equity_curve: List[float], risk_free_rate: float) -> float:
    """
    Calculate Sharpe ratio (annualized).

    Sharpe = (return - risk_free_rate) / volatility
    """
    if len(equity_curve) < 2:
        return 0.0

    # Calculate daily returns
    returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i-1] > 0:
            ret = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
            returns.append(ret)

    if not returns:
        return 0.0

    # Annualized Sharpe (assuming daily data)
    avg_return = np.mean(returns)
    std_return = np.std(returns)

    if std_return == 0:
        return 0.0

    # Daily to annual: multiply by sqrt(252)
    sharpe = (avg_return * 252 - risk_free_rate) / (std_return * np.sqrt(252))
    return sharpe


def _calculate_sortino(equity_curve: List[float], risk_free_rate: float) -> float:
    """
    Calculate Sortino ratio (downside-deviation-adjusted return).

    Sortino = (return - risk_free_rate) / downside_deviation
    """
    if len(equity_curve) < 2:
        return 0.0

    # Calculate daily returns
    returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i-1] > 0:
            ret = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
            returns.append(ret)

    if not returns:
        return 0.0

    avg_return = np.mean(returns)

    # Calculate downside deviation (only negative returns)
    negative_returns = [r for r in returns if r < 0]
    if not negative_returns:
        return float('inf') if avg_return > risk_free_rate else 0.0

    downside_std = np.std(negative_returns)

    if downside_std == 0:
        return 0.0

    # Annualized Sortino
    sortino = (avg_return * 252 - risk_free_rate) / (downside_std * np.sqrt(252))
    return sortino


def _calculate_max_drawdown(equity_curve: List[float]) -> tuple:
    """
    Calculate maximum drawdown and duration.

    Returns:
        Tuple of (max_drawdown_as_decimal, duration_as_timedelta)
    """
    if len(equity_curve) < 2:
        return 0.0, timedelta(0)

    peak = equity_curve[0]
    max_dd = 0.0
    max_dd_duration = timedelta(0)
    current_dd_start = None

    for i, value in enumerate(equity_curve):
        if value > peak:
            peak = value
            current_dd_start = None

        drawdown = (peak - value) / peak if peak > 0 else 0

        if drawdown > 0:
            if current_dd_start is None:
                current_dd_start = i

            if drawdown > max_dd:
                max_dd = drawdown
                max_dd_duration = timedelta(seconds=(i - current_dd_start) * 3600)  # Assume hourly
        else:
            current_dd_start = None

    return max_dd, max_dd_duration


def _calculate_volatility(equity_curve: List[float]) -> float:
    """Calculate annualized volatility."""
    if len(equity_curve) < 2:
        return 0.0

    returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i-1] > 0:
            ret = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
            returns.append(ret)

    if not returns:
        return 0.0

    # Annualized volatility (assuming daily data)
    return np.std(returns) * np.sqrt(252)


def _calculate_max_exposure(result: BacktestResult) -> float:
    """Calculate maximum capital deployed."""
    max_exposure = 0.0

    for trade in result.executed_trades:
        if trade.size > max_exposure:
            max_exposure = trade.size

    return max_exposure


def _calculate_avg_exposure(result: BacktestResult) -> float:
    """Calculate average capital deployed."""
    if not result.executed_trades:
        return 0.0

    total_size = sum(t.size for t in result.executed_trades)
    return total_size / len(result.executed_trades)


def format_metrics(metrics: dict) -> str:
    """
    Format metrics for display.

    Args:
        metrics: Dictionary from compute_metrics()

    Returns:
        Formatted string representation
    """
    lines = [
        "=== Backtest Performance ===",
        "",
        "Returns:",
        f"  Total Return: {metrics['total_return_pct']:.2f}%",
        f"  Absolute Profit: ${metrics['absolute_profit']:.2f}",
        f"  Final Equity: ${metrics['final_equity']:.2f}",
        "",
        "Risk-Adjusted Metrics:",
        f"  Sharpe Ratio: {metrics['sharpe_ratio']:.2f}",
        f"  Sortino Ratio: {metrics['sortino_ratio']:.2f}",
        f"  Max Drawdown: {metrics['max_drawdown_pct']:.2f}%",
        f"  Volatility: {metrics['volatility']:.2f}%",
        "",
        "Trading Activity:",
        f"  Total Trades: {metrics['total_trades']}",
        f"  Win Rate: {metrics['win_rate_pct']:.1f}%",
        f"  Avg Trade Return: {metrics['avg_trade_return']:.2%}",
        f"  Skipped Trades: {metrics['skipped_trades']} ({metrics['skip_rate_pct']:.1f}%)",
        "",
        "Capital & Costs:",
        f"  Max Exposure: ${metrics['max_exposure']:.2f}",
        f"  Avg Exposure: ${metrics['avg_exposure']:.2f}",
        f"  Total Fees: ${metrics['total_fees']:.2f}",
    ]

    return "\n".join(lines)
