"""FVG Breakout Strategy - Rule-Based Trading System"""

from src.config import STRATEGY_CONFIG, BACKTEST_CONFIG, ALPACA_CONFIG, StrategyConfig, STRATEGY_CONFIG_V2
from src.pattern_detection import (
    PatternDetector,
    DailySetup,
    FairValueGap,
    TradeSetup,
    validate_trading_window
)
from src.backtest_engine import BacktestEngine, BacktestResult, TradeRecord
from src.analytics import PerformanceAnalyzer, plot_equity_curve, plot_r_multiple_distribution
from src.data_fetcher import AlpacaDataFetcher, CSVDataLoader, get_data

__all__ = [
    "STRATEGY_CONFIG",
    "BACKTEST_CONFIG",
    "ALPACA_CONFIG",
    "StrategyConfig",
    "STRATEGY_CONFIG_V2",
    "PatternDetector",
    "DailySetup",
    "FairValueGap",
    "TradeSetup",
    "validate_trading_window",
    "BacktestEngine",
    "BacktestResult",
    "TradeRecord",
    "PerformanceAnalyzer",
    "plot_equity_curve",
    "plot_r_multiple_distribution",
    "AlpacaDataFetcher",
    "CSVDataLoader",
    "get_data",
]
