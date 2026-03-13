"""Strategy framework for the Polymarket trading bot.

BaseStrategy: abstract base class defining the strategy interface.
MeanReversionStrategy: z-score based mean reversion on YES price.

Phase 1 stub: should_trade() uses a simple confidence threshold.
Full risk controls (max position, daily loss limit, cooldown) come in Phase 2.
"""
import statistics
from abc import ABC, abstractmethod
from collections import deque

from polymarket_bot.models import MarketState, Signal


class BaseStrategy(ABC):
    """Abstract strategy interface. All strategies must implement both methods."""

    @abstractmethod
    def generate_signal(self, market_state: MarketState) -> Signal | None:
        """Analyze market state and return a Signal, or None if no trade warranted."""
        ...

    @abstractmethod
    def should_trade(self, signal: Signal, market_state: MarketState) -> bool:
        """Return True if the bot should act on this signal given current market state."""
        ...


class MeanReversionStrategy(BaseStrategy):
    """Mean reversion strategy using z-score of YES price vs rolling mean.

    Logic:
      - Track rolling window of yes_price observations per market_id
      - Compute z = (current - mean) / std
      - z < -z_entry → price is unusually LOW → BUY_YES (expect reversion up)
      - z > +z_entry → price is unusually HIGH → BUY_NO (expect reversion down)
      - No signal when window not yet filled or std == 0

    Phase 1 stub: should_trade() returns True when confidence >= 0.3.
    Phase 2 will replace this with real risk controls.
    """

    def __init__(
        self,
        window: int = 20,
        z_entry: float = 2.0,
        z_exit: float = 0.5,
    ) -> None:
        self.window = window
        self.z_entry = z_entry
        self.z_exit = z_exit
        # Per-market price history: {market_id: deque of yes_prices}
        self._history: dict[str, deque] = {}

    def generate_signal(self, market_state: MarketState) -> Signal | None:
        """Generate a trading signal based on z-score of the yes_price."""
        mid = market_state.yes_price
        market_id = market_state.market_id

        # Get or create the history buffer for this market
        buf = self._history.setdefault(market_id, deque(maxlen=self.window))
        buf.append(mid)

        # Need a full window before generating signals
        if len(buf) < self.window:
            return None

        mean = statistics.mean(buf)
        # statistics.stdev requires at least 2 values; deque maxlen >= window >= 3
        std = statistics.stdev(buf)

        # Guard: flat price series produces no useful signal
        if std == 0:
            return None

        z = (mid - mean) / std

        if z < -self.z_entry:
            # Price is unusually low → expect reversion up → BUY YES token
            return Signal(
                market_id=market_id,
                direction="BUY_YES",
                confidence=min(abs(z) / (self.z_entry * 2), 1.0),
                price=mid,
                reason=f"z-score={z:.2f} < -{self.z_entry} (mean={mean:.3f}, std={std:.3f})",
            )

        if z > self.z_entry:
            # Price is unusually high → expect reversion down → BUY NO token
            return Signal(
                market_id=market_id,
                direction="BUY_NO",
                confidence=min(z / (self.z_entry * 2), 1.0),
                price=market_state.no_price,
                reason=f"z-score={z:.2f} > {self.z_entry} (mean={mean:.3f}, std={std:.3f})",
            )

        return None

    def should_trade(self, signal: Signal, market_state: MarketState) -> bool:
        """Phase 1 stub: trade when confidence meets minimum threshold.

        Phase 2 will add: max position check, daily loss limit, cooldown period.
        """
        return signal.confidence >= 0.3

    def get_z_score(self, market_id: str) -> float | None:
        """Return the current z-score for market_id, or None if window not yet filled.

        Used by Backtester to detect z_exit take-profit conditions without
        requiring a new signal to be generated.
        """
        buf = self._history.get(market_id)
        if buf is None or len(buf) < self.window:
            return None
        mean = statistics.mean(buf)
        std = statistics.stdev(buf)
        if std == 0:
            return None
        current = buf[-1]  # most recently added price
        return (current - mean) / std


class MomentumStrategy(BaseStrategy):
    """Momentum strategy using dual EMA crossover on yes_price.

    Algorithm:
      - Collect long_window observations to bootstrap both EMAs (same seed value)
      - After bootstrap: apply EMA recurrence each tick
        short_ema = short_alpha * price + (1 - short_alpha) * short_ema
        long_ema  = long_alpha  * price + (1 - long_alpha)  * long_ema
        where alpha = 2 / (window + 1)
      - Crossover UP  (short crossed above long): BUY_YES
      - Crossover DOWN (short crossed below long): BUY_NO
      - No signal on same-side continuation (spread same sign as previous)
      - Confidence = min(abs(spread) * confidence_scale, 1.0)

    Phase 2 stub: should_trade() uses confidence >= 0.3.
    Risk controls applied by RiskManager gate in run_loop().
    """

    def __init__(
        self,
        short_window: int = 5,
        long_window: int = 20,
        confidence_scale: float = 10.0,
    ) -> None:
        if short_window >= long_window:
            raise ValueError(
                f"short_window ({short_window}) must be < long_window ({long_window})"
            )
        self.short_window = short_window
        self.long_window = long_window
        self.short_alpha = 2.0 / (short_window + 1)
        self.long_alpha = 2.0 / (long_window + 1)
        self.confidence_scale = confidence_scale
        # Per-market state: {market_id: {"short": float|None, "long": float|None,
        #                                "count": int, "prices": list[float]}}
        self._state: dict[str, dict] = {}

    def generate_signal(self, market_state: MarketState) -> Signal | None:
        """Generate a BUY_YES or BUY_NO signal on EMA crossover, else None."""
        price = market_state.yes_price
        market_id = market_state.market_id

        st = self._state.setdefault(market_id, {
            "short": None,
            "long": None,
            "prev_spread": None,
            "count": 0,
            "prices": [],
        })
        st["count"] += 1

        # Bootstrap phase: accumulate until long_window prices available
        if st["count"] <= self.long_window:
            st["prices"].append(price)
            if st["count"] == self.long_window:
                # Seed BOTH EMAs with SMA of bootstrap prices to prevent false crossover
                seed = sum(st["prices"]) / len(st["prices"])
                st["short"] = seed
                st["long"] = seed
            return None

        # EMA update: apply recurrence formula
        st["short"] = self.short_alpha * price + (1.0 - self.short_alpha) * st["short"]
        st["long"] = self.long_alpha * price + (1.0 - self.long_alpha) * st["long"]

        spread = st["short"] - st["long"]
        prev_spread = st["prev_spread"]
        st["prev_spread"] = spread

        # First post-bootstrap tick: establish spread direction, no crossover possible yet
        if prev_spread is None:
            return None

        # Crossover UP: short EMA crosses from below to above long EMA
        if prev_spread <= 0.0 and spread > 0.0:
            confidence = min(abs(spread) * self.confidence_scale, 1.0)
            return Signal(
                market_id=market_id,
                direction="BUY_YES",
                confidence=confidence,
                price=market_state.yes_price,
                reason=(
                    f"EMA crossover UP: short={st['short']:.4f} > long={st['long']:.4f}"
                ),
            )

        # Crossover DOWN: short EMA crosses from above to below long EMA
        if prev_spread >= 0.0 and spread < 0.0:
            confidence = min(abs(spread) * self.confidence_scale, 1.0)
            return Signal(
                market_id=market_id,
                direction="BUY_NO",
                confidence=confidence,
                price=market_state.no_price,
                reason=(
                    f"EMA crossover DOWN: short={st['short']:.4f} < long={st['long']:.4f}"
                ),
            )

        return None

    def should_trade(self, signal: Signal, market_state: MarketState) -> bool:
        """Confidence pre-filter. RiskManager.check() is the real gate in run_loop()."""
        return signal.confidence >= 0.3
