"""
Extended metrics computation for backtest results.

Computes: Sharpe ratio, max drawdown duration, daily PnL distribution,
exposure, avg time in trade, max consecutive wins/losses, expectancy,
max single position loss, avg trade % return.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .models import BacktestResult, TradeRecord

MS_PER_DAY = 24 * 3600 * 1000
BARS_PER_YEAR_30M = 17520  # 365 * 48


@dataclass
class DailyPnLStats:
    """Daily PnL distribution statistics."""
    mean: float = 0.0
    std: float = 0.0
    min_pnl: float = 0.0       # worst day
    max_pnl: float = 0.0       # best day
    skewness: float = 0.0
    kurtosis: float = 0.0
    percentiles: dict = field(default_factory=dict)  # {1,5,25,50,75,95,99}
    daily_pnls: list = field(default_factory=list)


@dataclass
class ExtendedMetrics:
    """All extended metrics computed from a BacktestResult."""
    # Basic (already on BacktestResult, copied here for completeness)
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    net_profit: float = 0.0
    net_profit_pct: float = 0.0
    profit_factor: float = 0.0
    avg_trade_pnl: float = 0.0
    max_drawdown: float = 0.0

    # Extended
    sharpe_ratio: float = 0.0
    max_dd_duration_bars: int = 0
    max_dd_duration_hours: float = 0.0
    exposure_pct: float = 0.0
    avg_time_in_trade_hours: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    expectancy: float = 0.0
    avg_trade_pct: float = 0.0
    max_single_position_loss: float = 0.0
    max_single_position_loss_pct: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    closed_trade_max_drawdown: float = 0.0

    # Daily PnL
    daily_pnl: Optional[DailyPnLStats] = None


def compute_extended_metrics(result: BacktestResult,
                             bar_interval_minutes: int = 30) -> ExtendedMetrics:
    """Compute all extended metrics from a BacktestResult."""
    m = ExtendedMetrics()

    # Copy basic metrics
    m.total_trades = result.total_trades
    m.winning_trades = result.winning_trades
    m.losing_trades = result.losing_trades
    m.win_rate = result.win_rate
    m.net_profit = result.net_profit
    m.net_profit_pct = result.net_profit_pct
    m.profit_factor = result.profit_factor
    m.avg_trade_pnl = result.avg_trade_pnl
    m.max_drawdown = result.max_drawdown
    m.closed_trade_max_drawdown = result.closed_trade_max_drawdown

    trades = result.trades
    if not trades:
        return m

    # Win/loss aggregates
    wins = [t for t in trades if t.pnl_net > 0]
    losses = [t for t in trades if t.pnl_net <= 0]

    m.avg_win = sum(t.pnl_net for t in wins) / len(wins) if wins else 0.0
    m.avg_loss = abs(sum(t.pnl_net for t in losses) / len(losses)) if losses else 0.0
    m.largest_win = max((t.pnl_net for t in wins), default=0.0)
    m.largest_loss = min((t.pnl_net for t in losses), default=0.0)

    # Expectancy
    wr = m.win_rate / 100.0
    m.expectancy = wr * m.avg_win - (1 - wr) * m.avg_loss

    # Max consecutive wins/losses
    m.max_consecutive_wins = _max_streak(trades, winning=True)
    m.max_consecutive_losses = _max_streak(trades, winning=False)

    # Avg trade % return
    trade_pcts = []
    for t in trades:
        entry_value = t.entry_price * t.entry_qty
        if entry_value > 0:
            trade_pcts.append(t.pnl_net / entry_value * 100)
    m.avg_trade_pct = sum(trade_pcts) / len(trade_pcts) if trade_pcts else 0.0

    # Max single position loss
    if losses:
        worst = min(losses, key=lambda t: t.pnl_net)
        m.max_single_position_loss = worst.pnl_net
        entry_val = worst.entry_price * worst.entry_qty
        m.max_single_position_loss_pct = (
            worst.pnl_net / entry_val * 100 if entry_val > 0 else 0.0
        )

    # Avg time in trade (in hours)
    durations = [
        (t.exit_bar_index - t.entry_bar_index) * bar_interval_minutes / 60.0
        for t in trades
    ]
    m.avg_time_in_trade_hours = sum(durations) / len(durations) if durations else 0.0

    # Exposure: fraction of bars where a position was open
    m.exposure_pct = _compute_exposure(trades, result.equity_curve)

    # Sharpe ratio (30m bar returns)
    m.sharpe_ratio = _compute_sharpe(result.equity_curve)

    # Max drawdown duration
    m.max_dd_duration_bars, m.max_dd_duration_hours = _compute_max_dd_duration(
        result.equity_curve, bar_interval_minutes
    )

    # Daily PnL distribution
    m.daily_pnl = _compute_daily_pnl(result.equity_curve)

    return m


def _max_streak(trades: list[TradeRecord], winning: bool) -> int:
    """Count longest consecutive winning or losing streak."""
    max_s = 0
    current = 0
    for t in trades:
        is_win = t.pnl_net > 0
        if is_win == winning:
            current += 1
            max_s = max(max_s, current)
        else:
            current = 0
    return max_s


def _compute_exposure(trades: list[TradeRecord], equity_curve: list) -> float:
    """Fraction of equity_curve bars where at least one position was open."""
    if not equity_curve or not trades:
        return 0.0

    total_bars = len(equity_curve)
    # Build set of bar indices where position is open
    bars_in_position = 0
    for t in trades:
        bars_in_position += (t.exit_bar_index - t.entry_bar_index)

    # This over-counts when multiple layers overlap, but gives a reasonable estimate
    return min(100.0, bars_in_position / total_bars * 100) if total_bars > 0 else 0.0


def _compute_sharpe(equity_curve: list) -> float:
    """Sharpe ratio from bar-level equity returns. Annualized for 30m bars."""
    if len(equity_curve) < 2:
        return 0.0

    returns = []
    for i in range(1, len(equity_curve)):
        prev_eq = equity_curve[i - 1][1]
        curr_eq = equity_curve[i][1]
        if prev_eq > 0:
            returns.append((curr_eq - prev_eq) / prev_eq)

    if not returns:
        return 0.0

    mean_r = sum(returns) / len(returns)
    if len(returns) < 2:
        return 0.0

    var = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
    std_r = math.sqrt(var) if var > 0 else 0.0

    if std_r == 0:
        return 0.0

    return mean_r / std_r * math.sqrt(BARS_PER_YEAR_30M)


def _compute_max_dd_duration(equity_curve: list,
                              bar_interval_minutes: int) -> tuple[int, float]:
    """Longest drawdown duration: bars between peak and recovery to new peak."""
    if len(equity_curve) < 2:
        return 0, 0.0

    peak = equity_curve[0][1]
    peak_idx = 0
    max_duration = 0

    for i, (ts, eq) in enumerate(equity_curve):
        if eq >= peak:
            duration = i - peak_idx
            if duration > max_duration:
                max_duration = duration
            peak = eq
            peak_idx = i

    # Check if still in drawdown at end
    final_duration = len(equity_curve) - 1 - peak_idx
    if final_duration > max_duration:
        max_duration = final_duration

    hours = max_duration * bar_interval_minutes / 60.0
    return max_duration, hours


def _compute_daily_pnl(equity_curve: list) -> DailyPnLStats:
    """Compute daily PnL distribution from equity curve."""
    stats = DailyPnLStats()
    if len(equity_curve) < 2:
        return stats

    # Group equity by UTC day
    days = {}
    for ts, eq in equity_curve:
        day_key = _day_key(ts)
        if day_key not in days:
            days[day_key] = {'start': eq, 'end': eq}
        days[day_key]['end'] = eq

    # Compute daily PnL percentages
    sorted_days = sorted(days.keys())
    daily_pnls = []
    for dk in sorted_days:
        d = days[dk]
        if d['start'] > 0:
            pnl_pct = (d['end'] - d['start']) / d['start'] * 100
            daily_pnls.append(pnl_pct)

    if not daily_pnls:
        return stats

    stats.daily_pnls = daily_pnls
    n = len(daily_pnls)
    stats.mean = sum(daily_pnls) / n
    stats.min_pnl = min(daily_pnls)
    stats.max_pnl = max(daily_pnls)

    if n >= 2:
        var = sum((x - stats.mean) ** 2 for x in daily_pnls) / (n - 1)
        stats.std = math.sqrt(var) if var > 0 else 0.0

    # Skewness and kurtosis
    if n >= 3 and stats.std > 0:
        stats.skewness = (
            sum(((x - stats.mean) / stats.std) ** 3 for x in daily_pnls)
            * n / ((n - 1) * (n - 2))
        )
    if n >= 4 and stats.std > 0:
        m4 = sum((x - stats.mean) ** 4 for x in daily_pnls) / n
        stats.kurtosis = m4 / (stats.std ** 4) - 3.0  # excess kurtosis

    # Percentiles
    sorted_pnls = sorted(daily_pnls)
    for p in [1, 5, 25, 50, 75, 95, 99]:
        idx = int(p / 100 * (n - 1))
        idx = max(0, min(idx, n - 1))
        stats.percentiles[p] = sorted_pnls[idx]

    return stats


def _day_key(timestamp_ms: int) -> str:
    """Return 'YYYY-MM-DD' for the given timestamp."""
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")
