"""Backtesting engine for pmirror."""

from pmirror.backtest.engine import BacktestEngine, BacktestConfig, BacktestResult
from pmirror.backtest.runner import BacktestRunner, run_backtest
from pmirror.backtest.metrics import compute_metrics, format_metrics

__all__ = [
    "BacktestEngine",
    "BacktestConfig",
    "BacktestResult",
    "BacktestRunner",
    "run_backtest",
    "compute_metrics",
    "format_metrics",
]
