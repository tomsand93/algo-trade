"""
Candlestick Pro - Core Data Models

Defines the data structures used throughout the system.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Tuple
import math


class Direction(Enum):
    """Trade direction"""
    LONG = "long"
    SHORT = "short"


class PatternType(Enum):
    """Supported candlestick patterns"""
    ENGULFING = "engulfing"
    PIN_BAR = "pin_bar"
    MORNING_STAR = "morning_star"
    EVENING_STAR = "evening_star"
    INSIDE_BAR = "inside_bar"


class TimeFrameStyle(Enum):
    """Trading style based on timeframe"""
    SCALPING = "scalping"
    INTRADAY = "intraday"
    SWING = "swing"


@dataclass
class Candle:
    """OHLCV candle data"""
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None

    def __post_init__(self):
        """Validate candle data"""
        if self.high < max(self.open, self.close):
            raise ValueError(f"High {self.high} < max(open, close)")
        if self.low > min(self.open, self.close):
            raise ValueError(f"Low {self.low} > min(open, close)")
        if self.volume is not None and self.volume < 0:
            raise ValueError(f"Volume {self.volume} < 0")

    @property
    def range(self) -> float:
        """Candle range (high - low)"""
        return self.high - self.low

    @property
    def body(self) -> float:
        """Candle body (absolute close - open)"""
        return abs(self.close - self.open)

    @property
    def upper_wick(self) -> float:
        """Upper wick size"""
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        """Lower wick size"""
        return min(self.open, self.close) - self.low

    @property
    def is_bullish(self) -> bool:
        """Bullish candle (close > open)"""
        return self.close > self.open

    @property
    def body_ratio(self) -> float:
        """Body as ratio of range"""
        if self.range < 1e-10:
            return 0.0
        return self.body / self.range

    @property
    def datetime(self) -> datetime:
        """Timestamp as datetime object"""
        return datetime.fromtimestamp(self.timestamp / 1000)


@dataclass
class SupportResistanceLevel:
    """Support or resistance level"""
    price: float
    level_type: str  # 'support' or 'resistance'
    strength: int  # Number of touches/confirmations
    timestamp: int  # Last update timestamp


@dataclass
class TimeFrameAnalysis:
    """Analysis result for a single timeframe"""
    timeframe: str
    noise_score: float  # 0-1, lower is better (cleaner structure)
    trend_strength: float  # 0-1, higher is stronger trend
    volatility_ratio: float  # Current ATR / Average ATR
    has_clear_structure: bool  # Clear trend or range visible
    quality_score: float  # Combined score 0-1
    reason: str  # Explanation of quality assessment


@dataclass
class TradingIdea:
    """
    Complete trading signal with all required details.
    This is the main output of the strategy.
    """
    # Market Info
    symbol: str
    selected_timeframe: str
    timeframe_justification: str

    # Pattern Info
    pattern: PatternType
    pattern_description: str
    pattern_index: int  # Index in candle array

    # Trade Parameters
    direction: Direction
    entry_price: float
    entry_trigger: str  # How/when to enter

    # Risk Management
    stop_loss_price: float
    stop_loss_reasoning: str  # Why this SL invalidates the idea
    take_profit_prices: List[float]  # Can have multiple TP levels
    take_profit_reasoning: str  # Why these TP levels

    # Risk Metrics
    risk_amount: float  # Entry - SL (absolute)
    reward_amount: float  # TP - Entry (absolute, for primary TP)
    rr_ratio: float  # Reward/Risk ratio

    # Confidence
    confidence_level: str  # "Low", "Medium", "High"
    confidence_score: float  # 0.0 - 1.0

    # Additional Context
    filters_passed: List[str]
    filters_failed: List[str] = field(default_factory=list)
    atr_value: float = 0.0
    sr_levels_nearby: List[SupportResistanceLevel] = field(default_factory=list)
    timestamp: int = 0

    def __str__(self) -> str:
        """Human-readable trade idea"""
        output = [
            "=" * 70,
            f"TRADING IDEA - {self.symbol}",
            "=" * 70,
            "",
            f"Pattern: {self.pattern.value.upper()}",
            f"  {self.pattern_description}",
            "",
            f"Selected Timeframe: {self.selected_timeframe}",
            f"  Reason: {self.timeframe_justification}",
            "",
            f"Direction: {self.direction.value.upper()}",
            "",
            f"Entry: ${self.entry_price:.6f}",
            f"  Trigger: {self.entry_trigger}",
            "",
            f"Stop Loss: ${self.stop_loss_price:.6f}",
            f"  Reasoning: {self.stop_loss_reasoning}",
            "",
            f"Take Profit(s):",
        ]
        for i, tp in enumerate(self.take_profit_prices, 1):
            output.append(f"  TP{i}: ${tp:.6f}")
        output.append(f"  Reasoning: {self.take_profit_reasoning}")

        output.extend([
            "",
            f"Risk Metrics:",
            f"  Risk: ${self.risk_amount:.6f}",
            f"  Reward: ${self.reward_amount:.6f} (primary TP)",
            f"  R:R Ratio: 1:{self.rr_ratio:.2f}",
            "",
            f"Confidence: {self.confidence_level} ({self.confidence_score:.2%})",
            "",
            f"Filters Passed: {', '.join(self.filters_passed)}",
        ])

        if self.filters_failed:
            output.append(f"Filters Failed: {', '.join(self.filters_failed)}")

        output.append("=" * 70)

        return "\n".join(output)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "symbol": self.symbol,
            "selected_timeframe": self.selected_timeframe,
            "timeframe_justification": self.timeframe_justification,
            "pattern": self.pattern.value,
            "pattern_description": self.pattern_description,
            "direction": self.direction.value,
            "entry_price": self.entry_price,
            "entry_trigger": self.entry_trigger,
            "stop_loss_price": self.stop_loss_price,
            "stop_loss_reasoning": self.stop_loss_reasoning,
            "take_profit_prices": self.take_profit_prices,
            "take_profit_reasoning": self.take_profit_reasoning,
            "risk_amount": self.risk_amount,
            "reward_amount": self.reward_amount,
            "rr_ratio": self.rr_ratio,
            "confidence_level": self.confidence_level,
            "confidence_score": self.confidence_score,
            "filters_passed": self.filters_passed,
            "filters_failed": self.filters_failed,
            "atr_value": self.atr_value,
            "timestamp": self.timestamp,
        }


@dataclass
class BacktestConfig:
    """Configuration for backtesting"""
    symbol: str
    initial_capital: float = 100_000
    fee_pct: float = 0.001  # 0.1% per trade
    slippage_pct: float = 0.0005  # 0.05%
    min_rr_ratio: float = 2.0
    confidence_threshold: float = 0.5
    max_trades: int = 1000
    # Trailing stop settings
    use_trailing_stop: bool = True
    trailing_atr_distance: float = 1.5
    breakeven_at_rr: float = 1.0  # Move stop to breakeven after 1R profit
    # Confirmation candle settings
    use_confirmation: bool = True
    confirmation_window: int = 2  # Max candles to wait for confirmation
    # Multi-pattern mode
    use_multi_pattern: bool = True
    # Strict trend mode: require BOTH price AND EMA9 aligned with EMA21
    strict_trend: bool = False
    # Tiered exit settings (exit positions in multiple stages)
    use_tiered_exit: bool = False
    tiered_exits: List[Tuple[float, float]] = None  # List of (rr_level, percentage) tuples

    def __post_init__(self):
        if self.tiered_exits is None:
            # Default tiered exits: 40% at 1.5R, 30% at 2.5R, 30% at 3.5R
            self.tiered_exits = [(1.5, 0.40), (2.5, 0.30), (3.5, 0.30)]


@dataclass
class BacktestResult:
    """Results from backtesting"""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_return: float
    max_drawdown: float
    max_drawdown_pct: float
    avg_win: float
    avg_loss: float
    expectancy: float
    profit_factor: float
    total_fees: float
    equity_curve: List[float]
    trades: List[dict]

    def __str__(self) -> str:
        """Human-readable backtest summary"""
        return f"""
{'='*60}
BACKTEST RESULTS
{'='*60}

Total Trades:        {self.total_trades}
Winning Trades:      {self.winning_trades}
Losing Trades:       {self.losing_trades}
Win Rate:            {self.win_rate*100:.2f}%

Total Return:        {self.total_return*100:.2f}%
Max Drawdown:        {self.max_drawdown_pct:.2f}%

Average Win:         ${self.avg_win:.2f}
Average Loss:        ${self.avg_loss:.2f}
Expectancy:          ${self.expectancy:.2f} per trade
Profit Factor:       {self.profit_factor:.2f}

Total Fees Paid:     ${self.total_fees:.2f}
{'='*60}
"""
