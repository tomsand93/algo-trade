"""
FVG Breakout Strategy - Configuration
=====================================
Single rule-based trading strategy with zero discretion.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from datetime import time


@dataclass
class StrategyConfig:
    """
    Strategy Configuration - DO NOT MODIFY PARAMETERS
    All values are fixed per strategy specification.
    """

    # Market Session
    market_open: time = time(9, 30)      # NYSE Open
    market_close: time = time(16, 0)     # NYSE Close
    setup_end: time = time(9, 35)        # End of 5-min candle analysis

    # Timeframes
    setup_timeframe: str = "5Min"        # For day_high/day_low
    execution_timeframe: str = "1Min"    # For pattern detection & entry

    # Risk Management (FIXED - No optimization allowed)
    risk_reward_ratio: float = 3.0       # 3:1 R:R ratio
    max_trades_per_symbol_per_day: int = 1  # Strict limit

    # Pattern Rules
    min_displacement: float = 0.001      # Minimum price movement for FVG (0.1%)

    # Data Source
    data_provider: str = "alpaca"

    # Default Symbols
    symbols: List[str] = field(default_factory=lambda: [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"
    ])

    # ── V2 Quality Filters (defaults = disabled, reproduces V1 exactly) ──

    # Minimum FVG gap size as % of price (0.0 = disabled)
    min_fvg_gap_pct: float = 0.0

    # Minimum body/range ratio for displacement candle #2 (0.0 = disabled)
    min_displacement_body_ratio: float = 0.0

    # Require displacement candle #2 closes in trade direction
    require_displacement_direction: bool = False

    # Last allowed entry time as (hour, minute) tuple, None = disabled
    entry_cutoff_time: Optional[Tuple[int, int]] = None

    # Accept strong directional candle instead of strict engulfing
    relaxed_entry: bool = False

    # Minimum body/range ratio for relaxed entry candle
    min_directional_body_ratio: float = 0.40

    # Earlier EOD exit time, None = use last bar (default 16:00 close)
    eod_exit_time: Optional[time] = None

    # ── Structural Parameters (defaults = V1 behavior) ──

    # Max stop loss as % of entry price (0.0 = no limit)
    max_sl_pct: float = 0.0

    # SL placement: "c1" = candle 1 extreme (default), "c2" = candle 2 extreme (tighter)
    sl_placement: str = "c1"

    # Max bars to hold before forced exit (0 = hold until SL/TP/EOD)
    max_bars_held: int = 0


@dataclass
class BacktestConfig:
    """Backtesting Configuration"""

    start_date: str = "2023-01-01"
    end_date: str = "2024-12-31"

    # Execution
    slippage_bps: int = 0  # No slippage simulation (ideal fills)
    commission_per_share: float = 0.0  # Zero commission for analysis

    # Output
    save_trades: bool = True
    plot_equity_curve: bool = True


@dataclass
class AlpacaConfig:
    """Alpaca API Configuration"""

    base_url: str = "https://data.alpaca.markets"
    api_key: str = ""  # Set via environment variable
    api_secret: str = ""  # Set via environment variable


# Global configuration instances
STRATEGY_CONFIG = StrategyConfig()
BACKTEST_CONFIG = BacktestConfig()
ALPACA_CONFIG = AlpacaConfig()

# V2 preset - only the proven improvement (earlier EOD exit)
# Investigation showed all pattern-quality filters hurt win rate.
# eod_exit_time=15:30 is the only change that improved every metric:
#   42.1% -> 42.7% WR, 0.229R -> 0.234R, Sharpe 2.16 -> 2.22
STRATEGY_CONFIG_V2 = StrategyConfig(
    eod_exit_time=time(15, 30),
)
