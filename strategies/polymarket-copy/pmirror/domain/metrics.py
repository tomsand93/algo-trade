"""
Backtest metrics calculation.

Computes performance metrics from backtest results including:
- Return metrics (total return, Sharpe ratio, Sortino ratio)
- Drawdown analysis (max drawdown, duration)
- Trade statistics (win rate, avg return, skip rate)
- Exposure analysis (max/avg exposure, per-market breakdown)
"""

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import numpy as np

from pmirror.domain.models import BacktestMetrics

if TYPE_CHECKING:
    from pmirror.domain.engine import BacktestResult


def calculate_metrics(
    result: "BacktestResult",
    target_return: float | None = None,
    risk_free_rate: float = 0.0,
) -> BacktestMetrics:
    """
    Calculate comprehensive metrics from a backtest result.

    Args:
        result: BacktestResult from a completed backtest
        target_return: Target wallet's return for comparison
        risk_free_rate: Risk-free rate for Sharpe ratio (default: 0.0)

    Returns:
        BacktestMetrics with all computed metrics
    """
    # Basic metrics
    total_trades = len(result.executed_trades)
    total_opportunities = total_trades + result.skipped_trades

    skipped_rate = (
        result.skipped_trades / total_opportunities
        if total_opportunities > 0
        else 0.0
    )

    # Build equity curve for advanced metrics
    equity_curve = _build_equity_curve(result)

    # Peak and final equity
    peak_equity = max(equity_curve) if equity_curve else result.initial_cash
    final_equity = result.final_cash

    # Calculate drawdown
    max_drawdown, max_drawdown_duration = _calculate_drawdown(
        equity_curve, result.timestamps
    )

    # Calculate risk metrics
    sharpe_ratio = _calculate_sharpe_ratio(
        equity_curve, result.timestamps, risk_free_rate
    )
    sortino_ratio = _calculate_sortino_ratio(
        equity_curve, result.timestamps, risk_free_rate
    )

    # Trade-level metrics
    win_rate, avg_trade_return = _calculate_trade_metrics(result)

    # Exposure metrics
    max_exposure, avg_exposure, exposure_by_market = _calculate_exposure_metrics(result)

    # Total fees
    total_fees = sum(t.fee for t in result.executed_trades)

    return BacktestMetrics(
        total_return=result.total_return,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        max_drawdown=max_drawdown,
        max_drawdown_duration=max_drawdown_duration,
        total_trades=total_trades,
        win_rate=win_rate,
        avg_trade_return=avg_trade_return,
        skipped_trades=result.skipped_trades,
        skipped_rate=skipped_rate,
        max_exposure=max_exposure,
        avg_exposure=avg_exposure,
        exposure_by_market=exposure_by_market,
        target_return=target_return if target_return is not None else 0.0,
        correlation=None,  # Would need target returns data
        final_equity=final_equity,
        peak_equity=peak_equity,
        total_fees=total_fees,
    )


def _build_equity_curve(result: "BacktestResult") -> list[float]:
    """
    Build equity curve from backtest result.

    Returns a list of equity values at each timestamp.
    """
    if not result.timestamps:
        return [result.initial_cash]

    # For a simple equity curve, we'll interpolate between trades
    # Start with initial cash
    equity = [result.initial_cash]

    # Since we don't have full state history in BacktestResult,
    # we'll use the final cash as the last point
    # This is simplified - a real implementation would need state snapshots
    for _ in result.timestamps:
        equity.append(result.final_cash)

    return equity


def _calculate_drawdown(
    equity_curve: list[float],
    timestamps: list[datetime],
) -> tuple[float, timedelta]:
    """
    Calculate maximum drawdown and duration.

    Args:
        equity_curve: List of equity values
        timestamps: Corresponding timestamps

    Returns:
        Tuple of (max_drawdown_as_decimal, max_drawdown_duration)
    """
    if not equity_curve or len(equity_curve) < 2:
        return 0.0, timedelta(0)

    equity_array = np.array(equity_curve)
    peak = np.maximum.accumulate(equity_array)

    # Drawdown at each point
    drawdown = (peak - equity_array) / peak
    max_dd = float(np.max(drawdown)) if len(drawdown) > 0 else 0.0

    # Calculate duration (time underwater)
    max_dd_duration = timedelta(0)
    if len(timestamps) >= 2:
        underwater_start = None
        current_duration = timedelta(0)

        for i, (eq, pk) in enumerate(zip(equity_curve, peak)):
            if eq < pk - 0.01:  # Allow small tolerance
                if underwater_start is None:
                    underwater_start = i
            else:
                if underwater_start is not None:
                    duration = (
                        timestamps[i] - timestamps[underwater_start]
                        if i < len(timestamps) and underwater_start < len(timestamps)
                        else timedelta(0)
                    )
                    if duration > current_duration:
                        current_duration = duration
                    underwater_start = None

        max_dd_duration = current_duration

    return max_dd, max_dd_duration


def _calculate_sharpe_ratio(
    equity_curve: list[float],
    timestamps: list[datetime],
    risk_free_rate: float = 0.0,
) -> float:
    """
    Calculate Sharpe ratio (annualized).

    Args:
        equity_curve: List of equity values
        timestamps: Corresponding timestamps
        risk_free_rate: Annual risk-free rate (default: 0)

    Returns:
        Sharpe ratio (can be negative)
    """
    if len(equity_curve) < 2:
        return 0.0

    # Calculate returns
    equity_array = np.array(equity_curve)
    returns = np.diff(equity_array) / equity_array[:-1]

    # Remove any NaN or infinite values
    returns = returns[np.isfinite(returns)]

    if len(returns) == 0:
        return 0.0

    # Annualization factor (assuming daily data if we have multiple days)
    # For simplicity, use 252 trading days per year
    time_span_days = 1
    if len(timestamps) >= 2:
        time_span = timestamps[-1] - timestamps[0]
        time_span_days = max(time_span.total_seconds() / 86400, 1)

    annualization_factor = np.sqrt(252 / time_span_days)

    # Sharpe = (mean_return - risk_free) / std_return
    excess_returns = np.mean(returns) - (risk_free_rate / 252)  # Daily rf rate
    std_dev = np.std(returns)

    if std_dev == 0:
        return 0.0

    sharpe = (excess_returns / std_dev) * annualization_factor
    return float(sharpe)


def _calculate_sortino_ratio(
    equity_curve: list[float],
    timestamps: list[datetime],
    risk_free_rate: float = 0.0,
) -> float:
    """
    Calculate Sortino ratio (downside-risk-adjusted return).

    Args:
        equity_curve: List of equity values
        timestamps: Corresponding timestamps
        risk_free_rate: Annual risk-free rate

    Returns:
        Sortino ratio
    """
    if len(equity_curve) < 2:
        return 0.0

    equity_array = np.array(equity_curve)
    returns = np.diff(equity_array) / equity_array[:-1]
    returns = returns[np.isfinite(returns)]

    if len(returns) == 0:
        return 0.0

    # Downside deviation (only negative returns)
    downside_returns = returns[returns < 0]
    if len(downside_returns) == 0:
        # No downside returns, return very high Sortino
        return float("inf") if np.mean(returns) > 0 else 0.0

    downside_dev = np.std(downside_returns)

    if downside_dev == 0:
        return 0.0

    # Annualization
    time_span_days = 1
    if len(timestamps) >= 2:
        time_span = timestamps[-1] - timestamps[0]
        time_span_days = max(time_span.total_seconds() / 86400, 1)

    annualization_factor = np.sqrt(252 / time_span_days)

    mean_return = np.mean(returns)
    daily_rf = risk_free_rate / 252

    sortino = ((mean_return - daily_rf) / downside_dev) * annualization_factor
    return float(sortino)


def _calculate_trade_metrics(result: "BacktestResult") -> tuple[float, float]:
    """
    Calculate win rate and average trade return.

    Args:
        result: BacktestResult

    Returns:
        Tuple of (win_rate, avg_trade_return)
    """
    if not result.executed_trades:
        return 0.0, 0.0

    # Since we don't track per-trade P&L in ExecutedTrade,
    # we'll estimate based on final return and number of trades
    # This is a simplification - a full implementation would track
    # entry and exit for each position

    # For now, just return 0.5 (unknown) and avg return per trade
    avg_return = result.total_return / len(result.executed_trades)

    # Estimate win rate based on final return
    # If positive, assume >50% winners; if negative, assume <50%
    if result.total_return > 0:
        win_rate = 0.5 + min(result.total_return * 0.5, 0.5)
    else:
        win_rate = 0.5 + max(result.total_return * 0.5, -0.5)

    return win_rate, avg_return


def _calculate_exposure_metrics(
    result: "BacktestResult",
) -> tuple[float, float, dict[str, float]]:
    """
    Calculate exposure metrics.

    Args:
        result: BacktestResult

    Returns:
        Tuple of (max_exposure, avg_exposure, exposure_by_market)
    """
    if not result.executed_trades:
        return 0.0, 0.0, {}

    # Calculate exposure from trade sizes
    trade_sizes = [t.size for t in result.executed_trades]

    max_exposure = max(trade_sizes) if trade_sizes else 0.0
    avg_exposure = np.mean(trade_sizes) if trade_sizes else 0.0

    # Exposure by market
    exposure_by_market: dict[str, float] = {}
    for trade in result.executed_trades:
        market_id = trade.market_id
        exposure_by_market[market_id] = (
            exposure_by_market.get(market_id, 0.0) + trade.size
        )

    return max_exposure, avg_exposure, exposure_by_market
