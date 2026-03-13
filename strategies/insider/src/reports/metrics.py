"""
Performance metrics calculation and reporting.

Computes:
- CAGR, total return, max drawdown
- Win rate, profit factor, Sharpe ratio
- Exposure, turnover, statistics
- Benchmark comparison
"""
import logging
from datetime import date
from decimal import Decimal
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def calculate_sharpe_ratio(
    returns: List[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252
) -> float:
    """
    Calculate annualized Sharpe ratio.

    Args:
        returns: List of periodic returns
        risk_free_rate: Annual risk-free rate
        periods_per_year: Number of periods per year (252 for daily)

    Returns:
        Sharpe ratio
    """
    if not returns or len(returns) < 2:
        return 0.0

    returns_array = np.array(returns)
    avg_return = np.mean(returns_array)
    std_return = np.std(returns_array, ddof=1)

    if std_return == 0:
        return 0.0

    # Annualize
    annual_return = avg_return * periods_per_year
    annual_std = std_return * np.sqrt(periods_per_year)

    sharpe = (annual_return - risk_free_rate) / annual_std

    return sharpe


def calculate_sortino_ratio(
    returns: List[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252
) -> float:
    """
    Calculate annualized Sortino ratio (downside deviation).

    Args:
        returns: List of periodic returns
        risk_free_rate: Annual risk-free rate
        periods_per_year: Number of periods per year

    Returns:
        Sortino ratio
    """
    if not returns or len(returns) < 2:
        return 0.0

    returns_array = np.array(returns)
    avg_return = np.mean(returns_array)

    # Downside deviation (only negative returns)
    negative_returns = returns_array[returns_array < 0]
    if len(negative_returns) == 0:
        return float('inf') if avg_return > 0 else 0.0

    downside_std = np.std(negative_returns, ddof=1)

    if downside_std == 0:
        return 0.0

    # Annualize
    annual_return = avg_return * periods_per_year
    annual_downside_std = downside_std * np.sqrt(periods_per_year)

    sortino = (annual_return - risk_free_rate) / annual_downside_std

    return sortino


def calculate_max_drawdown(equity_curve: List[float]) -> Tuple[float, int, int]:
    """
    Calculate maximum drawdown and its location.

    Args:
        equity_curve: List of equity values

    Returns:
        Tuple of (max_drawdown_pct, peak_index, trough_index)
    """
    if not equity_curve:
        return 0.0, 0, 0

    equity_array = np.array(equity_curve)
    peaks = np.maximum.accumulate(equity_array)
    drawdowns = (equity_array - peaks) / peaks

    max_dd_idx = np.argmin(drawdowns)
    max_dd = drawdowns[max_dd_idx]

    # Find the peak before this trough
    peak_idx = np.argmax(equity_array[:max_dd_idx + 1])

    return float(max_dd), int(peak_idx), int(max_dd_idx)


def calculate_calmar_ratio(cagr: float, max_drawdown: float) -> float:
    """Calculate Calmar ratio (CAGR / abs(max drawdown))."""
    if max_drawdown == 0:
        return 0.0
    return cagr / abs(max_drawdown)


def compute_metrics(
    equity_curve: List[Tuple[date, Decimal]],
    trades: List[Dict[str, Any]],
    initial_equity: Decimal,
    benchmark_data: Optional[List[Tuple[date, float]]] = None,
) -> Dict[str, Any]:
    """
    Compute comprehensive performance metrics.

    Args:
        equity_curve: List of (date, equity) tuples
        trades: List of trade results
        initial_equity: Starting equity
        benchmark_data: Optional benchmark equity curve for comparison

    Returns:
        Dictionary of performance metrics
    """
    if not equity_curve:
        return {}

    # Convert to numeric arrays
    dates = [e[0] for e in equity_curve]
    equity_values = [float(e[1]) for e in equity_curve]

    # Basic return metrics
    final_equity = equity_values[-1]
    total_return = (final_equity - float(initial_equity)) / float(initial_equity)

    # Time period
    start_date = dates[0]
    end_date = dates[-1]
    days = (end_date - start_date).days
    years = days / 365.25

    # CAGR
    cagr = (final_equity / float(initial_equity)) ** (1 / years) - 1 if years > 0 else 0

    # Drawdown
    max_dd, peak_idx, trough_idx = calculate_max_drawdown(equity_values)

    # Returns for Sharpe/Sortino
    returns = []
    for i in range(1, len(equity_values)):
        if equity_values[i - 1] > 0:
            returns.append((equity_values[i] - equity_values[i - 1]) / equity_values[i - 1])

    sharpe = calculate_sharpe_ratio(returns)
    sortino = calculate_sortino_ratio(returns)
    calmar = calculate_calmar_ratio(cagr, max_dd)

    # Trade statistics
    n_trades = len(trades)
    if n_trades > 0:
        trade_pnls = [float(t.get("net_pnl", 0)) for t in trades]
        winning = [p for p in trade_pnls if p > 0]
        losing = [p for p in trade_pnls if p < 0]

        win_rate = len(winning) / n_trades
        avg_win = np.mean(winning) if winning else 0
        avg_loss = np.mean(losing) if losing else 0

        gross_profit = sum(winning)
        gross_loss = abs(sum(losing))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        avg_hold = np.mean([float(t.get("hold_bars", 0)) for t in trades])
    else:
        win_rate = 0
        avg_win = 0
        avg_loss = 0
        profit_factor = 0
        avg_hold = 0

    # Benchmark comparison
    benchmark_metrics = {}
    if benchmark_data:
        bm_equity = [e[1] for e in benchmark_data]
        bm_total_return = (bm_equity[-1] - bm_equity[0]) / bm_equity[0]
        bm_cagr = (bm_equity[-1] / bm_equity[0]) ** (1 / years) - 1 if years > 0 else 0
        bm_max_dd, _, _ = calculate_max_drawdown(bm_equity)

        benchmark_metrics = {
            "benchmark_total_return": bm_total_return,
            "benchmark_cagr": bm_cagr,
            "benchmark_max_drawdown": bm_max_dd,
            "excess_return": total_return - bm_total_return,
        }

    metrics = {
        "return_metrics": {
            "total_return": total_return,
            "cagr": cagr,
            "max_drawdown": max_dd,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
        },
        "trade_metrics": {
            "n_trades": n_trades,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "avg_hold_bars": avg_hold,
        },
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "days": days,
            "years": years,
        },
    }

    if benchmark_metrics:
        metrics["benchmark"] = benchmark_metrics

    return metrics


def run_parameter_sweep(
    signals: List[Any],
    start_date: date,
    end_date: date,
    price_provider: Any,
    parameter_grid: Dict[str, List[Any]],
) -> pd.DataFrame:
    """
    Run backtest over parameter grid.

    Args:
        signals: List of signals
        start_date: Backtest start date
        end_date: Backtest end date
        price_provider: Price data provider
        parameter_grid: Dictionary of parameter names to lists of values

    Returns:
        DataFrame with results for each parameter combination
    """
    from itertools import product
    from ..backtest.engine import BacktestEngine

    # Generate all parameter combinations
    param_names = list(parameter_grid.keys())
    param_values = [parameter_grid[name] for name in param_names]
    combinations = list(product(*param_values))

    results = []

    for i, combo in enumerate(combinations):
        params = dict(zip(param_names, combo))

        logger.info(f"Running combination {i + 1}/{len(combinations)}: {params}")

        try:
            # Convert parameters to Decimal for engine
            from decimal import Decimal
            engine_params = {}
            for k, v in params.items():
                if isinstance(v, float):
                    engine_params[k] = Decimal(str(v))
                else:
                    engine_params[k] = v

            engine = BacktestEngine(
                **{
                    k: v for k, v in engine_params.items()
                    if k in BacktestEngine.__init__.__code__.co_varnames
                },
                price_provider=price_provider,
            )

            result = engine.run(signals, start_date, end_date)

            row = {
                **params,
                "total_return": float(result["summary"]["total_return"]),
                "cagr": float(result["summary"]["cagr"]),
                "max_drawdown": float(result["summary"]["max_drawdown"]),
                "sharpe_ratio": result["summary"]["sharpe_ratio"],
                "n_trades": result["trades"]["n_trades"],
                "win_rate": float(result["trades"]["win_rate"]),
                "profit_factor": float(result["trades"]["profit_factor"]),
            }
            results.append(row)

        except Exception as e:
            logger.error(f"Failed for params {params}: {e}")

    df = pd.DataFrame(results)

    # Sort by CAGR descending
    df = df.sort_values("cagr", ascending=False)

    return df


def create_results_table(
    sweep_results: pd.DataFrame,
    output_path: str
) -> None:
    """
    Create formatted results table from parameter sweep.

    Args:
        sweep_results: DataFrame from run_parameter_sweep
        output_path: Path to save CSV
    """
    # Format numeric columns
    format_cols = {
        "total_return": "{:.2%}",
        "cagr": "{:.2%}",
        "max_drawdown": "{:.2%}",
        "sharpe_ratio": "{:.2f}",
        "win_rate": "{:.2%}",
        "profit_factor": "{:.2f}",
    }

    for col, fmt in format_cols.items():
        if col in sweep_results.columns:
            sweep_results[col] = sweep_results[col].apply(lambda x: fmt.format(x))

    sweep_results.to_csv(output_path, index=False)
    logger.info(f"Results table saved to {output_path}")
