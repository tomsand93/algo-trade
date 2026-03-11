"""
Candlestick Pro - 1-Minute Rule-Based Trading Strategy

A complete, mechanical trading system for 1-minute candles with:
- ADX-based regime filtering (TREND/RANGE/NO-TRADE)
- 3 specific setups (Trend Pullback, VWAP Reclaim/Rejection, ORB)
- Numeric candlestick pattern definitions
- Strict risk management
- Session and news filters
"""

from typing import List, Optional, Literal
from dataclasses import dataclass
from enum import Enum
from src.models import Candle, Direction


# =============================================================================
# ENUMS AND DATA STRUCTURES
# =============================================================================

class Regime(Enum):
    """Market regime based on ADX"""
    TREND = "trend"        # ADX >= 25
    RANGE = "range"        # ADX <= 18
    NO_TRADE = "chop"      # 18 < ADX < 25


class SetupType(Enum):
    """Trade setup types"""
    TREND_PULLBACK = "trend_pullback"      # Setup A: EMA 9/20 pullback
    VWAP_RECLAIM = "vwap_reclaim"          # Setup B1: VWAP reclaim
    VWAP_REJECTION = "vwap_rejection"      # Setup B2: VWAP rejection
    OPENING_RANGE = "opening_range"        # Setup C: ORB breakout


class SessionType(Enum):
    """Trading session types"""
    PRE_MARKET = "pre_market"
    REGULAR = "regular"
    AFTER_HOURS = "after_hours"


class MarketType(Enum):
    """Market categories for session filtering"""
    US_STOCKS = "us_stocks"
    FX_MAJOR = "fx_major"
    CRYPTO_MAJOR = "crypto_major"


@dataclass
class RegimeState:
    """Current market regime state"""
    regime: Regime
    adx_value: float
    adx_timeframe: str  # Timeframe ADX was calculated on
    timestamp: int


@dataclass
class OpeningRange:
    """Opening range levels"""
    high: float
    low: float
    start_ts: int
    end_ts: int
    is_valid: bool


@dataclass
class TradeSignal:
    """
    Complete trade signal output with all required details.
    This is what the strategy outputs when a valid setup is found.
    """
    # Signal Identity
    signal_id: str
    timestamp: int
    symbol: str

    # Regime and Context
    regime: Regime
    adx_value: float
    adx_timeframe: str
    setup_type: SetupType

    # Pattern Details
    pattern_type: str  # "pin_bar", "engulfing", "inside_bar_break"
    pattern_direction: Direction
    pattern_candle_index: int

    # Entry Parameters
    entry_price: float
    entry_trigger: str  # "market_close", "limit_50%", "breakout"

    # Stop Loss
    stop_loss_price: float
    stop_loss_atr: float  # Stop distance in ATR
    stop_loss_reasoning: str

    # Take Profits
    tp1_price: float
    tp1_rr: float  # Risk-reward for TP1

    # Risk Metrics
    risk_amount: float
    min_reward: float
    rr_ratio: float

    # Invalidation Conditions
    invalidation_conditions: List[str]

    # Decision
    decision: Literal["TAKE", "SKIP"]

    # Optional fields (must come last)
    # Pattern Validation (numeric)
    wick_to_body_ratio: Optional[float] = None  # For pin bars
    body_engulf_ratio: Optional[float] = None   # For engulfing
    inside_bar_contraction: Optional[float] = None  # For inside bar
    tp2_price: Optional[float] = None
    tp2_rr: Optional[float] = None
    trail_trigger_rr: Optional[float] = None  # When to start trailing
    skip_reason: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "signal_id": self.signal_id,
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "regime": self.regime.value,
            "adx_value": self.adx_value,
            "adx_timeframe": self.adx_timeframe,
            "setup_type": self.setup_type.value,
            "pattern_type": self.pattern_type,
            "pattern_direction": self.pattern_direction.value,
            "entry_price": self.entry_price,
            "entry_trigger": self.entry_trigger,
            "stop_loss_price": self.stop_loss_price,
            "stop_loss_atr": self.stop_loss_atr,
            "tp1_price": self.tp1_price,
            "tp1_rr": self.tp1_rr,
            "tp2_price": self.tp2_price,
            "tp2_rr": self.tp2_rr,
            "rr_ratio": self.rr_ratio,
            "decision": self.decision,
            "skip_reason": self.skip_reason,
        }

    def __str__(self) -> str:
        """Formatted output for trade signal"""
        lines = [
            "=" * 80,
            f"TRADE SIGNAL - {self.symbol} at {self.timestamp}",
            "=" * 80,
            "",
            "REGIME & CONTEXT",
            f"  Regime: {self.regime.value.upper()} (ADX: {self.adx_value:.2f} on {self.adx_timeframe})",
            f"  Setup: {self.setup_type.value.upper()}",
            "",
            "PATTERN DETECTED",
            f"  Type: {self.pattern_type}",
            f"  Direction: {self.pattern_direction.value.upper()}",
        ]

        if self.wick_to_body_ratio:
            lines.append(f"  Wick-to-Body Ratio: {self.wick_to_body_ratio:.2f}:1")
        if self.body_engulf_ratio:
            lines.append(f"  Body Engulf Ratio: {self.body_engulf_ratio:.2f}:1")
        if self.inside_bar_contraction:
            lines.append(f"  Inside Bar Contraction: {self.inside_bar_contraction:.1%}")

        lines.extend([
            "",
            "ENTRY & EXIT",
            f"  Entry: ${self.entry_price:.6f}",
            f"  Trigger: {self.entry_trigger}",
            f"  Stop Loss: ${self.stop_loss_price:.6f} ({self.stop_loss_atr:.2f} ATR)",
            f"    Reasoning: {self.stop_loss_reasoning}",
            f"  TP1: ${self.tp1_price:.6f} ({self.tp1_rr:.1f}R)",
        ])

        if self.tp2_price:
            lines.append(f"  TP2: ${self.tp2_price:.6f} ({self.tp2_rr:.1f}R)")
        if self.trail_trigger_rr:
            lines.append(f"  Trail: After +{self.trail_trigger_rr:.1f}R, trail EMA9")

        lines.extend([
            "",
            "RISK METRICS",
            f"  Risk: ${self.risk_amount:.6f} ({self.stop_loss_atr:.2f} ATR)",
            f"  R:R Ratio: 1:{self.rr_ratio:.2f}",
            "",
            "INVALIDATION CONDITIONS",
        ])

        for cond in self.invalidation_conditions:
            lines.append(f"  - {cond}")

        lines.extend([
            "",
            f"DECISION: {self.decision}",
        ])

        if self.skip_reason:
            lines.append(f"  Reason: {self.skip_reason}")

        lines.append("=" * 80)

        return "\n".join(lines)


# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

class OneMinuteConfig:
    """
    All numeric thresholds and configuration for the 1-minute strategy.
    Modify these values to adjust strategy behavior.
    """

    # =================== ADX REGIME FILTER ===================
    ADX_TIMEFRAME = "15m"  # Use 15m for regime (less noise than 1m)
    ADX_PERIOD = 14
    ADX_TREND_THRESHOLD = 25.0
    ADX_RANGE_THRESHOLD = 18.0

    # =================== EMAs ===================
    EMA_FAST = 9
    EMA_SLOW = 20
    EMA_TREND = 200

    # =================== VWAP ===================
    VWAP_ANCHOR = "session"  # Reset VWAP each session

    # =================== ATR ===================
    ATR_PERIOD = 14
    ATR_TIMEFRAME = "1m"  # Can also use 5m ATR mapped to 1m

    # =================== Opening Range ===================
    ORB_MINUTES = 5  # First 5 minutes define opening range
    ORB_BREAK_THRESHOLD_ATR = 0.1  # Must close outside OR by 0.1*ATR
    ORB_RETEST_WINDOW_MINUTES = 10  # Minutes after OR for valid retest

    # =================== PATTERN DEFINITIONS ===================

    # Pin Bar / Rejection Candle
    PIN_BAR_WICK_TO_BODY_MIN = 2.0  # Wick >= 2.0 * body
    PIN_BAR_BODY_POSITION_MAX = 0.30  # Body in top/bottom 30%
    PIN_BAR_CLOSE_ALIGNMENT_REQUIRED = True  # Close must be in trade direction

    # Engulfing Candle
    ENGULF_BODY_ENGULF_MIN = 0.80  # Engulfs >= 80% of prior body
    ENGULF_CLOSE_POSITION_MAX = 0.25  # Close within top/bottom 25%

    # Inside Bar Break
    INSIDE_BREAK_MIN_ATR = 0.1  # Break must exceed 0.1*ATR
    INSIDE_CLOSE_CONFIRMATION = True  # Must close in breakout direction

    # =================== SPREAD INVALIDATION ===================
    SPREAD_TO_ATR_MAX_RATIO = 0.15  # If spread > 15% of ATR, skip
    MIN_ROOM_TO_OPPOSING_LEVEL = 1.0  # Minimum 1R to opposing level

    # =================== VOLUME FILTER ===================
    # Only take trades when volume confirms the move
    VOLUME_FILTER_ENABLED = True
    VOLUME_MA_PERIOD = 20  # Moving average period for volume baseline
    VOLUME_MIN_RATIO = 1.3  # Volume must be >= 1.3x average (30% above average)

    # =================== HIGHER TIMEFRAME CONFIRMATION ===================
    # Only take trades aligned with higher timeframe trend
    HTF_TREND_CONFIRMATION_ENABLED = True
    HTF_TIMEFRAME = "15m"  # Use 15m for trend confirmation
    HTF_EMA_FAST = 9
    HTF_EMA_SLOW = 20
    HTF_EMA_TREND = 200

    # =================== RISK MANAGEMENT ===================
    RISK_PER_TRADE_PCT = 0.005  # 0.5% of equity (justify: allows 200+ trades before 50% drawdown)
    MAX_TRADES_PER_SESSION = 5
    DAILY_STOP_LOSS_R = -2.0  # Stop trading after -2R daily
    DAILY_STOP_LOSSES = 3  # Stop trading after 3 losses
    MAX_POSITIONS_PER_INSTRUMENT = 1

    # Stop Loss (in ATR)
    SL_MIN_ATR = 0.8
    SL_MAX_ATR = 1.5
    SL_SKIP_ABOVE_ATR = 1.5  # Skip if stop needs >1.5*ATR

    # Take Profit (in R)
    TP1_RR = 1.0
    TP2_RR = 2.0
    TRAIL_TRIGGER_RR = 1.5

    # =================== SESSION FILTERS ===================

    # US Stocks (NYSE/NASDAQ)
    US_STOCKS_REGULAR_START = "09:30"
    US_STOCKS_REGULAR_END = "16:00"
    US_STOCKS_IGNORE_FIRST_MINUTES = 3  # Skip first 3 minutes of open

    # Forex (GMT)
    FX_LONDON_OPEN = "08:00"
    FX_LONDON_CLOSE = "16:00"
    FX_NY_OPEN = "13:00"
    FX_NY_CLOSE = "21:00"

    # Crypto (UTC)
    CRYPTO_24_7 = True  # No session filter for crypto

    # =================== NEWS FILTER ===================
    NEWS_BUFFER_MINUTES = 10  # No trades within ±10 min of major news

    # =================== SETUP A: TREND PULLBACK ===================
    TREND_PULLBACK_VALUE_ZONE_ATR = 0.2  # EMA zone tolerance (original strict)
    TREND_PULLBACK_RELAXED_ZONE_ATR = 1.0  # Relaxed zone tolerance (for more signals)
    TREND_PULLBACK_MAX_RETRACE_ABOVE_EMA20 = 0.2  # Max close past EMA20
    USE_RELAXED_LOCATION = True  # Use relaxed zone for more trade opportunities

    # =================== SETUP B: VWAP ===================
    VWAP_HOLD_MINUTES = 1  # Must hold VWAP for 1 full minute
    VWAP_FAIL_PENETRATION_ATR = 0.1  # For rejection, fails if closes >0.1*ATR through
    VWAP_RANGE_MIN_RR = 1.5  # Minimum R:R for range fades

    # =================== SETUP C: ORB ===================
    ORB_STOP_MAX_ATR = 1.0  # Tighter stops for ORB
    ORB_STOP_MIN_ATR = 0.8
    ORB_TP1_RR = 2.0
    ORB_TP2_RR_TRAIL = 1.0  # After 1R, trail EMA9


# =============================================================================
# MAIN STRATEGY CLASS
# =============================================================================

class OneMinuteCandlestickStrategy:
    """
    Complete 1-minute candlestick trading strategy.

    Process:
    1. Check session and news filters
    2. Calculate ADX regime on context timeframe
    3. Calculate indicators (VWAP, EMAs, ATR)
    4. Check for opening range (if in first 15 minutes)
    5. For valid regime, scan for 3 setup types
    6. Validate candlestick pattern at setup location
    7. Calculate entry, SL, TP with risk rules
    8. Return signal or SKIP
    """

    def __init__(self, config: Optional[OneMinuteConfig] = None):
        """Initialize strategy with configuration."""
        self.cfg = config or OneMinuteConfig()

        # State tracking
        self.daily_trades = 0
        self.daily_losses = 0
        self.daily_r = 0.0
        self.open_positions = {}  # symbol -> position

        # Opening range tracking
        self.opening_ranges = {}  # symbol -> OpeningRange

    def analyze(
        self,
        candles_1m: List[Candle],
        candles_5m: Optional[List[Candle]] = None,
        candles_15m: Optional[List[Candle]] = None,
        symbol: str = "BTC/USD",
        market_type: MarketType = MarketType.CRYPTO_MAJOR,
        current_ts: int = 0
    ) -> Optional[TradeSignal]:
        """
        Main analysis entry point.

        Args:
            candles_1m: 1-minute candle data (minimum 200 candles)
            candles_5m: Optional 5-minute candles for ATR smoothing
            candles_15m: 15-minute candles for ADX regime
            symbol: Trading symbol
            market_type: Market category for session filtering
            current_ts: Current timestamp

        Returns:
            TradeSignal if valid setup, None otherwise
        """
        # Require minimum data
        if len(candles_1m) < 200:
            return None

        # Step 1: Session and news filters
        if not self._check_session_filter(candles_1m[-1], market_type):
            return self._skip_signal(symbol, current_ts, "Outside trading hours")

        if not self._check_news_filter(candles_1m[-1]):
            return self._skip_signal(symbol, current_ts, "News event within buffer")

        # Step 2: Calculate ADX regime
        candles_for_adx = candles_15m if candles_15m else candles_1m
        regime_state = self._calculate_regime(candles_for_adx)
        adx_tf = "15m" if candles_15m else "1m"

        if regime_state.regime == Regime.NO_TRADE:
            return self._skip_signal(
                symbol, current_ts,
                f"Chop regime (ADX: {regime_state.adx_value:.2f})"
            )

        # Step 3: Calculate indicators on 1m
        indicators = self._calculate_indicators(candles_1m, candles_5m)

        # Step 4: Check/update opening range
        self._update_opening_range(candles_1m, symbol, current_ts)

        # Step 5: Scan for setups based on regime
        setups = self._scan_setups(
            candles_1m,
            indicators,
            regime_state,
            symbol,
            adx_tf
        )

        # Step 6: Validate and return best setup
        for setup in setups:
            if self._validate_setup(setup, candles_1m, indicators, candles_15m):
                return self._create_trade_signal(setup, indicators, symbol, current_ts, regime_state, adx_tf)

        return None

    # ==================== REGIME CALCULATION ====================

    def _calculate_regime(self, candles: List[Candle]) -> RegimeState:
        """
        Calculate ADX-based regime.

        Returns:
            RegimeState with regime classification
        """
        if len(candles) < self.cfg.ADX_PERIOD + 1:
            return RegimeState(Regime.NO_TRADE, 0, self.cfg.ADX_TIMEFRAME, candles[-1].timestamp)

        adx_value = self._calculate_adx(candles, self.cfg.ADX_PERIOD)

        if adx_value >= self.cfg.ADX_TREND_THRESHOLD:
            regime = Regime.TREND
        elif adx_value <= self.cfg.ADX_RANGE_THRESHOLD:
            regime = Regime.RANGE
        else:
            regime = Regime.NO_TRADE

        return RegimeState(regime, adx_value, self.cfg.ADX_TIMEFRAME, candles[-1].timestamp)

    def _calculate_adx(self, candles: List[Candle], period: int) -> float:
        """
        Calculate ADX using standard method.

        ADX = SMA of DX values
        DX = 100 * +DI / (-DI + +DI) where +DI and -DI are smoothed directional movements
        """
        if len(candles) < period * 2:
            return 20.0  # Default middle value

        # Calculate True Range and Directional Movement
        tr_values = []
        plus_dm = []
        minus_dm = []

        for i in range(1, len(candles)):
            c_prev, c = candles[i-1], candles[i]

            tr = max(
                c.high - c.low,
                abs(c.high - c_prev.close),
                abs(c.low - c_prev.close)
            )
            tr_values.append(tr)

            up_move = c.high - c_prev.high
            down_move = c_prev.low - c.low

            if up_move > down_move and up_move > 0:
                plus_dm.append(up_move)
            else:
                plus_dm.append(0)

            if down_move > up_move and down_move > 0:
                minus_dm.append(down_move)
            else:
                minus_dm.append(0)

        # Smooth with Wilder's smoothing
        def smooth(values: List[float], period: int) -> List[float]:
            if len(values) < period:
                return [0] * len(values)
            result = [sum(values[:period]) / period]
            for i in range(period, len(values)):
                result.append((result[-1] * (period - 1) + values[i]) / period)
            return result

        smoothed_tr = smooth(tr_values, period)
        smoothed_plus_dm = smooth(plus_dm, period)
        smoothed_minus_dm = smooth(minus_dm, period)

        # Calculate +DI and -DI
        plus_di = []
        minus_di = []

        for i in range(len(smoothed_tr)):
            if smoothed_tr[i] > 0:
                plus_di.append(100 * smoothed_plus_dm[i] / smoothed_tr[i])
                minus_di.append(100 * smoothed_minus_dm[i] / smoothed_tr[i])
            else:
                plus_di.append(0)
                minus_di.append(0)

        # Calculate DX and ADX
        dx_values = []
        for i in range(len(plus_di)):
            di_sum = plus_di[i] + minus_di[i]
            if di_sum > 0:
                dx = 100 * abs(plus_di[i] - minus_di[i]) / di_sum
            else:
                dx = 0
            dx_values.append(dx)

        # ADX is SMA of DX
        adx_period = min(period, len(dx_values))
        if len(dx_values) >= adx_period:
            adx = sum(dx_values[-adx_period:]) / adx_period
        else:
            adx = 20.0

        return adx

    # ==================== INDICATOR CALCULATION ====================

    @dataclass
    class Indicators:
        """All indicators for current bar"""
        vwap: float
        ema9: float
        ema20: float
        ema200: float
        atr: float
        volume_ma: float  # Volume moving average for volume filter
        rsi: Optional[float] = None

    def _calculate_indicators(
        self,
        candles_1m: List[Candle],
        candles_5m: Optional[List[Candle]] = None
    ) -> 'OneMinuteCandlestickStrategy.Indicators':
        """Calculate all required indicators."""
        # VWAP (session-based)
        vwap = self._calculate_vwap_session(candles_1m)

        # EMAs
        ema9 = self._calculate_ema(candles_1m, self.cfg.EMA_FAST)
        ema20 = self._calculate_ema(candles_1m, self.cfg.EMA_SLOW)
        ema200 = self._calculate_ema(candles_1m, self.cfg.EMA_TREND)

        # ATR
        atr = self._calculate_atr(candles_1m, self.cfg.ATR_PERIOD)

        # Optional RSI (momentum filter)
        rsi = self._calculate_rsi(candles_1m, 14)

        # Volume MA for volume filter
        volume_ma = self._calculate_sma([c.volume or 0 for c in candles_1m], self.cfg.VOLUME_MA_PERIOD)

        return self.Indicators(vwap, ema9, ema20, ema200, atr, volume_ma, rsi)

    def _calculate_ema(self, candles: List[Candle], period: int) -> float:
        """Calculate EMA for given period."""
        if len(candles) < period:
            return candles[-1].close

        multiplier = 2 / (period + 1)
        ema = sum(c.close for c in candles[:period]) / period

        for c in candles[period:]:
            ema = (c.close - ema) * multiplier + ema

        return ema

    def _calculate_sma(self, values: List[float], period: int) -> float:
        """Calculate Simple Moving Average for given period."""
        if len(values) < period:
            return values[-1] if values else 0
        return sum(values[-period:]) / period

    def _calculate_atr(self, candles: List[Candle], period: int) -> float:
        """Calculate ATR using Wilder's smoothing."""
        if len(candles) < period + 1:
            return (candles[-1].high - candles[-1].low)

        true_ranges = []
        for i in range(1, len(candles)):
            tr = max(
                candles[i].high - candles[i].low,
                abs(candles[i].high - candles[i-1].close),
                abs(candles[i].low - candles[i-1].close)
            )
            true_ranges.append(tr)

        atr = sum(true_ranges[:period]) / period
        for tr in true_ranges[period:]:
            atr = (atr * (period - 1) + tr) / period

        return atr

    def _calculate_rsi(self, candles: List[Candle], period: int) -> Optional[float]:
        """Calculate RSI."""
        if len(candles) < period + 1:
            return None

        gains = []
        losses = []

        for i in range(1, len(candles)):
            change = candles[i].close - candles[i-1].close
            gains.append(max(change, 0))
            losses.append(max(-change, 0))

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        for gain, loss in zip(gains[period:], losses[period:]):
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def _calculate_vwap_session(self, candles: List[Candle]) -> float:
        """
        Calculate VWAP for current session.
        Simplified: uses last 100 candles as session approximation.
        In production, use actual session start time.
        """
        session_candles = candles[-min(390, len(candles)):]  # 1 trading day max

        total_pv = sum((c.high + c.low + c.close) / 3 * c.volume for c in session_candles if c.volume)
        total_volume = sum(c.volume for c in session_candles if c.volume)

        if total_volume == 0:
            return candles[-1].close

        return total_pv / total_volume

    # ==================== OPENING RANGE ====================

    def _update_opening_range(self, candles: List[Candle], symbol: str, current_ts: int):
        """Track opening range for first N minutes."""
        if len(candles) < self.cfg.ORB_MINUTES:
            return

        # Check if we need to initialize ORB
        if symbol not in self.opening_ranges:
            # Initialize ORB after first 5 minutes
            or_candles = candles[-self.cfg.ORB_MINUTES:]
            orb_high = max(c.high for c in or_candles)
            orb_low = min(c.low for c in or_candles)

            self.opening_ranges[symbol] = OpeningRange(
                high=orb_high,
                low=orb_low,
                start_ts=or_candles[0].timestamp,
                end_ts=or_candles[-1].timestamp,
                is_valid=True
            )

    # ==================== SETUP SCANNING ====================

    @dataclass
    class SetupCandidate:
        """Potential trade setup"""
        setup_type: SetupType
        direction: Direction
        candle_index: int
        entry_price: float
        entry_trigger: str
        stop_loss_price: float
        pattern_type: str
        pattern_validation: dict

    def _scan_setups(
        self,
        candles: List[Candle],
        indicators: 'OneMinuteCandlestickStrategy.Indicators',
        regime: RegimeState,
        symbol: str,
        adx_tf: str
    ) -> List['OneMinuteCandlestickStrategy.SetupCandidate']:
        """
        Scan for valid setups based on regime.

        TREND regime: Check Setup A (Trend Pullback) and B1 (VWAP Reclaim)
        RANGE regime: Check Setup B2 (VWAP Rejection) and C (ORB if early)
        """
        candidates = []
        i = len(candles) - 1

        # Check trend direction for TREND regime
        trend_direction = self._get_trend_direction(indicators)

        if regime.regime == Regime.TREND:
            # Setup A: Trend Pullback to EMA 9/20
            pullback = self._check_trend_pullback(candles, indicators, i, trend_direction)
            if pullback:
                candidates.append(pullback)

            # Setup B1: VWAP Reclaim (trend continuation)
            reclaim = self._check_vwap_reclaim(candles, indicators, i, trend_direction)
            if reclaim:
                candidates.append(reclaim)

        elif regime.regime == Regime.RANGE:
            # Setup B2: VWAP Rejection (range fade)
            rejection = self._check_vwap_rejection(candles, indicators, i)
            if rejection:
                candidates.append(rejection)

        # Setup C: Opening Range Breakout (first 15 minutes only)
        if self._is_in_orb_window(candles[-1]):
            orb = self._check_orb_breakout(candles, indicators, i, symbol)
            if orb:
                candidates.append(orb)

        return candidates

    def _get_trend_direction(self, ind: 'OneMinuteCandlestickStrategy.Indicators') -> Optional[Direction]:
        """Determine trend direction from EMA alignment."""
        current_close = ind.ema9  # Use EMA9 as proxy for current price

        if current_close > ind.ema200 and ind.ema9 > ind.ema20:
            return Direction.LONG
        elif current_close < ind.ema200 and ind.ema9 < ind.ema20:
            return Direction.SHORT

        return None

    # ==================== SETUP A: TREND PULLBACK ====================

    def _check_trend_pullback(
        self,
        candles: List[Candle],
        ind: 'OneMinuteCandlestickStrategy.Indicators',
        i: int,
        trend_direction: Optional[Direction]
    ) -> Optional['OneMinuteCandlestickStrategy.SetupCandidate']:
        """
        Setup A: Trend Pullback to EMA 9/20 zone.

        Long bias: Price > EMA200 and EMA9 > EMA20
        Short bias: Price < EMA200 and EMA9 < EMA20

        Pullback condition: Price in EMA9-EMA20 zone or tags EMA20
        Trigger: Approved candlestick pattern at/near EMA zone

        RELAXED MODE: Uses wider ATR band (1.0*ATR) instead of strict EMA zone.
        This generates more signals by allowing patterns near the EMA zone.
        """
        if trend_direction is None:
            return None

        c = candles[i]
        ema_zone_high = max(ind.ema9, ind.ema20)
        ema_zone_low = min(ind.ema9, ind.ema20)

        # Check if price is in pullback zone
        if self.cfg.USE_RELAXED_LOCATION:
            # Relaxed mode: Allow price within 1.0*ATR of EMA zone
            zone_tolerance = ind.atr * self.cfg.TREND_PULLBACK_RELAXED_ZONE_ATR
            near_ema_zone = (c.close >= ema_zone_low - zone_tolerance and
                           c.close <= ema_zone_high + zone_tolerance)
        else:
            # Strict mode: Price must be IN EMA zone or within 0.2*ATR of EMA20
            in_value_zone = ema_zone_low <= c.close <= ema_zone_high
            near_ema_zone = in_value_zone or abs(c.close - ind.ema20) < ind.atr * self.cfg.TREND_PULLBACK_VALUE_ZONE_ATR

        if not near_ema_zone:
            return None

        # Check for pullback pattern
        pattern = self._detect_pattern_at_location(candles, i, trend_direction, ind)

        if not pattern:
            return None

        # Calculate entry and stop
        entry_price = c.close  # Conservative: enter on close
        stop_loss_price = self._calculate_pullback_stop(candles, ind, i, trend_direction)

        # Validate stop distance
        stop_distance = abs(entry_price - stop_loss_price)
        stop_atr = stop_distance / ind.atr

        if stop_atr > self.cfg.SL_SKIP_ABOVE_ATR:
            return None

        return self.SetupCandidate(
            setup_type=SetupType.TREND_PULLBACK,
            direction=trend_direction,
            candle_index=i,
            entry_price=entry_price,
            entry_trigger="market_close",
            stop_loss_price=stop_loss_price,
            pattern_type=pattern["type"],
            pattern_validation=pattern["validation"]
        )

    def _calculate_pullback_stop(
        self,
        candles: List[Candle],
        ind: 'OneMinuteCandlestickStrategy.Indicators',
        i: int,
        direction: Direction
    ) -> float:
        """Calculate stop loss for pullback setup."""
        c = candles[i]

        if direction == Direction.LONG:
            # Below swing low of pullback or trigger wick
            swing_low = min(c.low, min(candles[j].low for j in range(max(0, i-5), i+1)))
            stop = min(swing_low, ind.ema20) - ind.atr * 0.1
        else:
            # Above swing high
            swing_high = max(c.high, max(candles[j].high for j in range(max(0, i-5), i+1)))
            stop = max(swing_high, ind.ema20) + ind.atr * 0.1

        # Ensure stop is within bounds
        entry = c.close
        stop_distance = abs(stop - entry)
        min_stop = ind.atr * self.cfg.SL_MIN_ATR
        max_stop = ind.atr * self.cfg.SL_MAX_ATR

        if stop_distance < min_stop:
            return entry - (min_stop if direction == Direction.LONG else -min_stop)
        if stop_distance > max_stop:
            return entry - (max_stop if direction == Direction.LONG else -max_stop)

        return stop

    # ==================== SETUP B: VWAP ====================

    def _check_vwap_reclaim(
        self,
        candles: List[Candle],
        ind: 'OneMinuteCandlestickStrategy.Indicators',
        i: int,
        trend_direction: Optional[Direction]
    ) -> Optional['OneMinuteCandlestickStrategy.SetupCandidate']:
        """
        Setup B1: VWAP Reclaim (trend continuation).

        Price was below VWAP, reclaims with bullish trigger,
        holds above for 1+ full candle.
        """
        if trend_direction is None:
            return None

        if trend_direction != Direction.LONG:
            return None  # Only long reclaim for now

        # Check recent price action: was below VWAP, now reclaiming
        if not (candles[i-1].close < ind.vwap and candles[i].close > ind.vwap):
            return None

        # Check for reclaim pattern
        pattern = self._detect_pattern_at_location(candles, i, Direction.LONG, ind)
        if not pattern:
            return None

        entry_price = candles[i].close
        stop_loss_price = ind.vwap - ind.atr * 0.8

        return self.SetupCandidate(
            setup_type=SetupType.VWAP_RECLAIM,
            direction=Direction.LONG,
            candle_index=i,
            entry_price=entry_price,
            entry_trigger="market_close",
            stop_loss_price=stop_loss_price,
            pattern_type=pattern["type"],
            pattern_validation=pattern["validation"]
        )

    def _check_vwap_rejection(
        self,
        candles: List[Candle],
        ind: 'OneMinuteCandlestickStrategy.Indicators',
        i: int
    ) -> Optional['OneMinuteCandlestickStrategy.SetupCandidate']:
        """
        Setup B2: VWAP Rejection (range fade).

        Price tags VWAP, prints rejection candle,
        fails to close through by >0.1*ATR.
        """
        c = candles[i]

        # Check if tagging VWAP
        if abs(c.close - ind.vwap) > ind.atr * 0.3:
            return None

        # Determine rejection direction
        if c.open > ind.vwap and c.close < ind.vwap:
            direction = Direction.SHORT
            rejection_body = c.open - c.close
        elif c.open < ind.vwap and c.close > ind.vwap:
            direction = Direction.LONG
            rejection_body = c.close - c.open
        else:
            return None

        # Check rejection strength
        if rejection_body < ind.atr * 0.2:
            return None

        # Validate as rejection pattern
        pattern = self._detect_pattern_at_location(candles, i, direction, ind)
        if not pattern:
            return None

        entry_price = c.close
        if direction == Direction.LONG:
            stop_loss_price = c.low - ind.atr * 0.5
        else:
            stop_loss_price = c.high + ind.atr * 0.5

        return self.SetupCandidate(
            setup_type=SetupType.VWAP_REJECTION,
            direction=direction,
            candle_index=i,
            entry_price=entry_price,
            entry_trigger="market_close",
            stop_loss_price=stop_loss_price,
            pattern_type=pattern["type"],
            pattern_validation=pattern["validation"]
        )

    # ==================== SETUP C: OPENING RANGE ====================

    def _is_in_orb_window(self, candle: Candle) -> bool:
        """Check if we're in ORB trading window (first 15 minutes)."""
        # Simplified: check if we have less than 15 candles
        # In production, use actual time
        return False  # Placeholder

    def _check_orb_breakout(
        self,
        candles: List[Candle],
        ind: 'OneMinuteCandlestickStrategy.Indicators',
        i: int,
        symbol: str
    ) -> Optional['OneMinuteCandlestickStrategy.SetupCandidate']:
        """Setup C: Opening Range Breakout."""
        if symbol not in self.opening_ranges:
            return None

        orb = self.opening_ranges[symbol]
        c = candles[i]

        # Check for breakout
        is_bullish_break = c.close > orb.high + ind.atr * self.cfg.ORB_BREAK_THRESHOLD_ATR
        is_bearish_break = c.close < orb.low - ind.atr * self.cfg.ORB_BREAK_THRESHOLD_ATR

        if not (is_bullish_break or is_bearish_break):
            return None

        direction = Direction.LONG if is_bullish_break else Direction.SHORT

        # Validate pattern
        pattern = self._detect_pattern_at_location(candles, i, direction, ind)
        if not pattern:
            return None

        entry_price = c.close
        if direction == Direction.LONG:
            stop_loss_price = orb.low
        else:
            stop_loss_price = orb.high

        return self.SetupCandidate(
            setup_type=SetupType.OPENING_RANGE,
            direction=direction,
            candle_index=i,
            entry_price=entry_price,
            entry_trigger="market_close",
            stop_loss_price=stop_loss_price,
            pattern_type=pattern["type"],
            pattern_validation=pattern["validation"]
        )

    # ==================== PATTERN DETECTION ====================

    def _detect_pattern_at_location(
        self,
        candles: List[Candle],
        i: int,
        direction: Direction,
        ind: 'OneMinuteCandlestickStrategy.Indicators'
    ) -> Optional[dict]:
        """
        Detect approved candlestick patterns at setup location.

        Returns:
            dict with "type" and "validation" data, or None
        """
        if i < 1:
            return None

        # Try each pattern type
        patterns = [
            self._check_pin_bar(candles, i, direction, ind),
            self._check_engulfing(candles, i, direction, ind),
            self._check_inside_bar_break(candles, i, direction, ind),
        ]

        for pattern in patterns:
            if pattern:
                return pattern

        return None

    def _check_pin_bar(
        self,
        candles: List[Candle],
        i: int,
        direction: Direction,
        ind: 'OneMinuteCandlestickStrategy.Indicators'
    ) -> Optional[dict]:
        """
        Check for Pin Bar / Rejection Candle.

        Rules:
        - Wick >= 2.0 * body
        - Body in top 30% (bull) or bottom 30% (bear)
        - Close in direction of trade
        - Must occur at actual level
        """
        c = candles[i]

        # Calculate pattern metrics
        body = abs(c.close - c.open)
        total_range = c.high - c.low
        upper_wick = c.high - max(c.open, c.close)
        lower_wick = min(c.open, c.close) - c.low

        if total_range < 1e-10 or body < 1e-10:
            return None

        wick_to_body = max(upper_wick, lower_wick) / body
        body_position_top = upper_wick / total_range
        body_position_bottom = lower_wick / total_range

        # Validate pattern structure
        is_bullish_pin = (
            direction == Direction.LONG and
            wick_to_body >= self.cfg.PIN_BAR_WICK_TO_BODY_MIN and
            lower_wick > upper_wick and
            body_position_bottom <= self.cfg.PIN_BAR_BODY_POSITION_MAX and
            c.is_bullish
        )

        is_bearish_pin = (
            direction == Direction.SHORT and
            wick_to_body >= self.cfg.PIN_BAR_WICK_TO_BODY_MIN and
            upper_wick > lower_wick and
            body_position_top <= self.cfg.PIN_BAR_BODY_POSITION_MAX and
            not c.is_bullish
        )

        if not (is_bullish_pin or is_bearish_pin):
            return None

        return {
            "type": "pin_bar",
            "validation": {
                "wick_to_body_ratio": wick_to_body,
                "body_position_top": body_position_top,
                "body_position_bottom": body_position_bottom,
            }
        }

    def _check_engulfing(
        self,
        candles: List[Candle],
        i: int,
        direction: Direction,
        ind: 'OneMinuteCandlestickStrategy.Indicators'
    ) -> Optional[dict]:
        """
        Check for Engulfing Candle.

        Rules:
        - Body engulfs prior candle body by >= 80%
        - Close near extreme: within top/bottom 25%
        - Must align with setup context
        """
        if i < 1:
            return None

        c1, c2 = candles[i-1], candles[i]

        body1 = abs(c1.close - c1.open)
        body2 = abs(c2.close - c2.open)

        if body1 < 1e-10:
            return None

        engulf_ratio = body2 / body1
        close_position = (c2.close - c2.low) / (c2.high - c2.low) if c2.high > c2.low else 0.5

        is_bullish_engulf = (
            direction == Direction.LONG and
            not c1.is_bullish and
            c2.is_bullish and
            c2.open <= c1.close and
            c2.close >= c1.open and
            engulf_ratio >= 1 + self.cfg.ENGULF_BODY_ENGULF_MIN and
            close_position >= 1 - self.cfg.ENGULF_CLOSE_POSITION_MAX
        )

        is_bearish_engulf = (
            direction == Direction.SHORT and
            c1.is_bullish and
            not c2.is_bullish and
            c2.open >= c1.close and
            c2.close <= c1.open and
            engulf_ratio >= 1 + self.cfg.ENGULF_BODY_ENGULF_MIN and
            close_position <= self.cfg.ENGULF_CLOSE_POSITION_MAX
        )

        if not (is_bullish_engulf or is_bearish_engulf):
            return None

        return {
            "type": "engulfing",
            "validation": {
                "body_engulf_ratio": engulf_ratio,
                "close_position": close_position,
            }
        }

    def _check_inside_bar_break(
        self,
        candles: List[Candle],
        i: int,
        direction: Direction,
        ind: 'OneMinuteCandlestickStrategy.Indicators'
    ) -> Optional[dict]:
        """
        Check for Inside Bar Break (compression).

        Rules:
        - Current bar high < prior high AND low > prior low
        - Entry on break with follow-through
        - Break must exceed 0.1*ATR and close in direction
        """
        if i < 2:
            return None

        mother = candles[i-1]
        inside = candles[i]
        current = candles[i]

        # Check for inside bar structure
        is_inside = (inside.high < mother.high and inside.low > mother.low)

        if not is_inside:
            return None

        # Check for breakout
        is_bullish_break = (
            direction == Direction.LONG and
            current.close > mother.high + ind.atr * self.cfg.INSIDE_BREAK_MIN_ATR
        )

        is_bearish_break = (
            direction == Direction.SHORT and
            current.close < mother.low - ind.atr * self.cfg.INSIDE_BREAK_MIN_ATR
        )

        if not (is_bullish_break or is_bearish_break):
            return None

        contraction = inside.range / mother.range if mother.range > 0 else 0

        return {
            "type": "inside_bar_break",
            "validation": {
                "inside_bar_contraction": contraction,
                "break_size_atr": abs(current.close - mother.close) / ind.atr,
            }
        }

    # ==================== VALIDATION ====================

    def _validate_setup(
        self,
        setup: 'OneMinuteCandlestickStrategy.SetupCandidate',
        candles: List[Candle],
        ind: 'OneMinuteCandlestickStrategy.Indicators',
        candles_15m: Optional[List[Candle]] = None
    ) -> bool:
        """Validate setup meets all risk and filter criteria."""
        # Check stop distance
        risk = abs(setup.entry_price - setup.stop_loss_price)
        risk_atr = risk / ind.atr

        if risk_atr < self.cfg.SL_MIN_ATR or risk_atr > self.cfg.SL_SKIP_ABOVE_ATR:
            return False

        # Check volume filter
        if self.cfg.VOLUME_FILTER_ENABLED:
            pattern_candle = candles[setup.candle_index]
            if pattern_candle.volume and pattern_candle.volume < ind.volume_ma * self.cfg.VOLUME_MIN_RATIO:
                return False  # Volume too low, skip trade

        # Check higher timeframe trend confirmation
        if self.cfg.HTF_TREND_CONFIRMATION_ENABLED and candles_15m and len(candles_15m) >= 200:
            if not self._check_htf_trend_alignment(setup.direction, candles_15m):
                return False  # Trade not aligned with higher timeframe trend

        # Check daily limits
        if self.daily_trades >= self.cfg.MAX_TRADES_PER_SESSION:
            return False

        if self.daily_losses >= self.cfg.DAILY_STOP_LOSSES:
            return False

        if self.daily_r <= self.cfg.DAILY_STOP_LOSS_R:
            return False

        return True

    def _check_htf_trend_alignment(self, direction: Direction, candles_htf: List[Candle]) -> bool:
        """
        Check if trade direction aligns with higher timeframe trend.

        For LONG: EMA9 > EMA20 > EMA200 (uptrend)
        For SHORT: EMA9 < EMA20 < EMA200 (downtrend)
        """
        ema9 = self._calculate_ema(candles_htf, self.cfg.HTF_EMA_FAST)
        ema20 = self._calculate_ema(candles_htf, self.cfg.HTF_EMA_SLOW)
        ema200 = self._calculate_ema(candles_htf, self.cfg.HTF_EMA_TREND)

        if direction == Direction.LONG:
            # Uptrend: fast > slow > trend
            return ema9 > ema20 and ema20 > ema200
        else:  # SHORT
            # Downtrend: fast < slow < trend
            return ema9 < ema20 and ema20 < ema200

    def _create_trade_signal(
        self,
        setup: 'OneMinuteCandlestickStrategy.SetupCandidate',
        ind: 'OneMinuteCandlestickStrategy.Indicators',
        symbol: str,
        ts: int,
        regime: RegimeState,
        adx_tf: str
    ) -> TradeSignal:
        """Create final trade signal with all parameters."""
        risk = abs(setup.entry_price - setup.stop_loss_price)
        risk_atr = risk / ind.atr

        # Calculate take profits
        tp1 = setup.entry_price + (risk * self.cfg.TP1_RR if setup.direction == Direction.LONG else -risk * self.cfg.TP1_RR)
        tp2 = setup.entry_price + (risk * self.cfg.TP2_RR if setup.direction == Direction.LONG else -risk * self.cfg.TP2_RR)

        # Build invalidation conditions
        invalidations = [
            f"Stop loss hit at ${setup.stop_loss_price:.6f}",
            f"Daily loss exceeds {self.cfg.DAILY_STOP_LOSS_R}R",
        ]

        if setup.setup_type == SetupType.TREND_PULLBACK:
            invalidations.append(f"Price closes beyond EMA20 by >{self.cfg.TREND_PULLBACK_MAX_RETRACE_ABOVE_EMA20}*ATR")

        # Extract pattern validation
        pattern_validation = setup.pattern_validation

        return TradeSignal(
            signal_id=f"{symbol}_{ts}_{setup.setup_type.value}",
            timestamp=ts,
            symbol=symbol,
            regime=regime.regime,
            adx_value=regime.adx_value,
            adx_timeframe=adx_tf,
            setup_type=setup.setup_type,
            pattern_type=setup.pattern_type,
            pattern_direction=setup.direction,
            pattern_candle_index=setup.candle_index,
            wick_to_body_ratio=pattern_validation.get("wick_to_body_ratio"),
            body_engulf_ratio=pattern_validation.get("body_engulf_ratio"),
            inside_bar_contraction=pattern_validation.get("inside_bar_contraction"),
            entry_price=setup.entry_price,
            entry_trigger=setup.entry_trigger,
            stop_loss_price=setup.stop_loss_price,
            stop_loss_atr=risk_atr,
            stop_loss_reasoning=f"Beyond pullback structure, {risk_atr:.2f}*ATR",
            tp1_price=tp1,
            tp1_rr=self.cfg.TP1_RR,
            tp2_price=tp2,
            tp2_rr=self.cfg.TP2_RR,
            trail_trigger_rr=self.cfg.TRAIL_TRIGGER_RR,
            risk_amount=risk,
            min_reward=risk * self.cfg.TP1_RR,
            rr_ratio=self.cfg.TP1_RR,
            invalidation_conditions=invalidations,
            decision="TAKE",
            skip_reason=None
        )

    def _skip_signal(self, symbol: str, ts: int, reason: str) -> TradeSignal:
        """Create a SKIP signal for logging."""
        return TradeSignal(
            signal_id=f"{symbol}_{ts}_skip",
            timestamp=ts,
            symbol=symbol,
            regime=Regime.NO_TRADE,
            adx_value=0,
            adx_timeframe="",
            setup_type=SetupType.TREND_PULLBACK,
            pattern_type="none",
            pattern_direction=Direction.LONG,
            pattern_candle_index=-1,
            entry_price=0,
            entry_trigger="",
            stop_loss_price=0,
            stop_loss_atr=0,
            stop_loss_reasoning="",
            tp1_price=0,
            tp1_rr=0,
            tp2_price=0,
            tp2_rr=0,
            trail_trigger_rr=0,
            risk_amount=0,
            min_reward=0,
            rr_ratio=0,
            invalidation_conditions=[],
            decision="SKIP",
            skip_reason=reason
        )

    # ==================== FILTERS ====================

    def _check_session_filter(self, candle: Candle, market_type: MarketType) -> bool:
        """
        Check if current time is within valid trading session.

        TODO(human): Implement the session filter logic.

        The strategy currently returns True (always valid), which means
        trades can be taken at any time. You need to implement proper
        session filtering based on the market type.

        Your task: Implement session validation logic that checks if the
        candle timestamp falls within valid trading hours for each market type.

        Guidance:
        - Extract the time from candle.timestamp (it's in milliseconds since epoch)
        - Convert to the appropriate timezone for the market:
          * US Stocks: Eastern Time (ET)
          * FX: GMT
          * Crypto: UTC (24/7, no filter needed)
        - For each market type, check if the time is within valid hours:
          * US Stocks: 09:30-16:00 ET, skip first 3 minutes
          * FX: London (08:00-16:00 GMT) or NY overlap (13:00-21:00 GMT)
          * Crypto: Always return True (24/7)
        - Consider datetime handling carefully (timezone, datetime module)
        - Return False if outside valid session, True if valid

        The config class has these constants you can reference:
          - US_STOCKS_REGULAR_START = "09:30"
          - US_STOCKS_REGULAR_END = "16:00"
          - US_STOCKS_IGNORE_FIRST_MINUTES = 3
        """
        # Placeholder: in production, check actual time against session
        # TODO(human): Replace this with your implementation
        return True

    def _check_news_filter(self, candle: Candle) -> bool:
        """Check if major news event is within buffer."""
        # Placeholder: in production, check economic calendar
        return True


# =============================================================================
# PSEUDOCODE SUMMARY
# =============================================================================

"""
PSEUDOCODE FOR 1-MINUTE CANDLESTICK STRATEGY
=============================================

FUNCTION analyze_1m_strategy(candles_1m, candles_15m, symbol):
    # Step 1: Session and News Filters
    IF NOT is_valid_session_time(candles_1m[-1], symbol.market_type):
        RETURN SKIP("Outside trading hours")

    IF is_news_event_within_buffer(candles_1m[-1]):
        RETURN SKIP("News event within ±10 minutes")

    # Step 2: Calculate Regime
    adx_15m = calculate_ADX(candles_15m, period=14)

    IF adx_15m >= 25:
        regime = "TREND"
    ELSE IF adx_15m <= 18:
        regime = "RANGE"
    ELSE:
        RETURN SKIP("Chop regime (18 < ADX < 25)")

    # Step 3: Calculate Indicators on 1m
    vwap = calculate_VWAP_session(candles_1m)
    ema9 = calculate_EMA(candles_1m, 9)
    ema20 = calculate_EMA(candles_1m, 20)
    ema200 = calculate_EMA(candles_1m, 200)
    atr_1m = calculate_ATR(candles_1m, 14)

    # Step 4: Determine Trend Direction
    IF close > ema200 AND ema9 > ema20:
        trend_bias = "LONG"
    ELSE IF close < ema200 AND ema9 < ema20:
        trend_bias = "SHORT"
    ELSE:
        trend_bias = NULL

    # Step 5: Scan for Setups
    candidates = []

    IF regime == "TREND" AND trend_bias IS NOT NULL:
        # Setup A: Trend Pullback
        IF is_in_ema_zone(close, ema9, ema20, atr_1m):
            pattern = detect_pattern_at_level(candles_1m, trend_bias)
            IF pattern IS NOT NULL:
                entry = close
                stop = calculate_pullback_stop(candles_1m, trend_bias, ema20, atr_1m)
                IF (abs(stop - entry) / atr_1m) <= 1.5:
                    candidates.append({type: "TREND_PULLBACK", entry, stop, pattern})

        # Setup B1: VWAP Reclaim
        IF was_below_vwap_prev AND close > vwap:
            pattern = detect_pattern_at_level(candles_1m, "LONG")
            IF pattern IS NOT NULL:
                candidates.append({type: "VWAP_RECLAIM", entry: close, stop: vwap - 0.8*atr})

    ELSE IF regime == "RANGE":
        # Setup B2: VWAP Rejection
        IF abs(close - vwap) < 0.3*atr:
            direction = detect_rejection_direction(candles_1m[-1])
            pattern = detect_pattern_at_level(candles_1m, direction)
            IF pattern IS NOT NULL:
                candidates.append({type: "VWAP_REJECTION", entry, stop, pattern})

    # Setup C: Opening Range (first 15 min only)
    IF is_in_first_15min(candles_1m):
        orb = calculate_opening_range(candles_1m, 5)
        IF close > orb.high + 0.1*atr OR close < orb.low - 0.1*atr:
            direction = "LONG" IF close > orb.high ELSE "SHORT"
            pattern = detect_pattern_at_level(candles_1m, direction)
            IF pattern IS NOT NULL:
                candidates.append({type: "ORB", entry: close, stop: opposite_orb_side, pattern})

    # Step 6: Validate Best Candidate
    FOR candidate IN candidates:
        risk = abs(candidate.entry - candidate.stop)
        risk_atr = risk / atr_1m

        IF risk_atr < 0.8 OR risk_atr > 1.5:
            CONTINUE  # Skip invalid stop distance

        IF NOT check_pattern_validation(candidate.pattern, atr_1m):
            CONTINUE

        # Step 7: Calculate Risk Parameters
        tp1 = entry + sign * risk * 1.0
        tp2 = entry + sign * risk * 2.0

        # Step 8: Output Signal
        RETURN {
            regime: regime,
            adx: adx_15m,
            setup_type: candidate.type,
            pattern: candidate.pattern.type,
            entry: candidate.entry,
            stop: candidate.stop,
            tp1: tp1,
            tp2: tp2,
            risk_atr: risk_atr,
            rr: 2.0,
            decision: "TAKE"
        }

    RETURN SKIP("No valid setup found")


FUNCTION detect_pattern_at_level(candles, direction, atr):
    # Try each pattern type in order

    # 1. Pin Bar
    IF wick_to_body >= 2.0 AND body_in_correct_position AND close_aligned:
        RETURN {type: "pin_bar", wick_to_body: ratio}

    # 2. Engulfing
    IF body_engulfs_prior >= 80% AND close_near_extreme:
        RETURN {type: "engulfing", engulf_ratio: ratio}

    # 3. Inside Bar Break
    IF is_inside_bar AND breaks_mother_by >= 0.1*atr AND closes_in_direction:
        RETURN {type: "inside_bar_break", contraction: ratio}

    RETURN NULL


FUNCTION check_pattern_validation(pattern, atr):
    # Spread invalidation
    IF spread > 0.15 * atr:
        RETURN False

    # Room to opposing level
    IF distance_to_opposing_level < 1.0 * risk:
        RETURN False

    RETURN True
"""
