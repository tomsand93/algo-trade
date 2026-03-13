"""Domain models module for pmirror."""

from pmirror.domain.models import (
    BacktestMetrics,
    BacktestState,
    ExecutedTrade,
    Market,
    Position,
    Trade,
)

from pmirror.domain.normalize import (
    normalize_trades,
    validate_trades,
    deduplicate_trades,
    deduplicate_dataframe,
    aggregate_trades_by_market,
    filter_trades,
    compute_trade_statistics,
    merge_trade_dataframes,
    DuplicateTradeError,
    ValidationError,
)

__all__ = [
    "Market",
    "Trade",
    "Position",
    "ExecutedTrade",
    "BacktestState",
    "BacktestMetrics",
    "normalize_trades",
    "validate_trades",
    "deduplicate_trades",
    "deduplicate_dataframe",
    "aggregate_trades_by_market",
    "filter_trades",
    "compute_trade_statistics",
    "merge_trade_dataframes",
    "DuplicateTradeError",
    "ValidationError",
]
