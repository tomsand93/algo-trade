"""Technical indicators for orderbook strategy."""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class MarketState:
    """Current market state for strategy."""

    # Price range
    range_high: float = 0.0
    range_low: float = float("inf")
    range_trades: deque = field(default_factory=lambda: deque())

    # Orderbook depth
    best_bid: float | None = None
    best_ask: float | None = None
    bid_depth: float = 0.0  # Sum size at K bid levels
    ask_depth: float = 0.0  # Sum size at K ask levels

    # Imbalance
    imbalance: float = 0.0

    # Delta (aggressive flow)
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    delta: float = 0.0

    # Sweep detection state
    last_sweep_high: float | None = None
    last_sweep_low: float | None = None
    last_sweep_time: datetime | None = None
    last_sweep_side: str | None = None  # "buy" or "sell"

    # Absorption state
    in_absorption: bool = False
    absorption_start: datetime | None = None

    # Depth tracking for absorption detection
    prev_ask_depth: float = 0.0
    prev_bid_depth: float = 0.0


class IndicatorEngine:
    """Compute indicators from orderbook and trade events."""

    def __init__(
        self,
        range_window_s: int = 60,
        depth_levels: int = 5,
        delta_window_s: int = 1,
        wall_mult: float = 3.0,
        wall_lookback_s: int = 5,
    ):
        self.range_window = timedelta(seconds=range_window_s)
        self.depth_levels = depth_levels
        self.delta_window = timedelta(seconds=delta_window_s)
        self.wall_mult = wall_mult
        self.wall_lookback = timedelta(seconds=wall_lookback_s)

        self.state = MarketState()
        self.delta_trades = deque()  # (timestamp, side, volume)

    def on_book_snapshot(self, snapshot, current_time: datetime) -> None:
        """Update orderbook state from snapshot."""
        # Update best bid/ask
        if snapshot.bids:
            self.state.best_bid = snapshot.bids[0].price
        if snapshot.asks:
            self.state.best_ask = snapshot.asks[0].price

        # Compute depth at K levels
        self.state.prev_bid_depth = self.state.bid_depth
        self.state.prev_ask_depth = self.state.ask_depth

        bid_levels = snapshot.bids[: self.depth_levels]
        ask_levels = snapshot.asks[: self.depth_levels]

        self.state.bid_depth = sum(level.size for level in bid_levels)
        self.state.ask_depth = sum(level.size for level in ask_levels)

        # Compute imbalance
        total = self.state.bid_depth + self.state.ask_depth
        if total > 0:
            self.state.imbalance = (self.state.bid_depth - self.state.ask_depth) / total
        else:
            self.state.imbalance = 0.0

    def on_trade(self, trade, current_time: datetime, snapshot_mid: float) -> None:
        """Update trade-based indicators."""
        # Store previous range high/low for sweep detection
        prev_range_high = self.state.range_high
        prev_range_low = self.state.range_low

        # Update range
        cutoff = current_time - self.range_window
        self.state.range_trades.append((current_time, trade.price))

        # Prune old trades
        while self.state.range_trades and self.state.range_trades[0][0] < cutoff:
            self.state.range_trades.popleft()

        # Compute range
        if self.state.range_trades:
            prices = [p for _, p in self.state.range_trades]
            self.state.range_high = max(prices)
            self.state.range_low = min(prices)

        # Check if this trade broke the range (for sweep detection)
        self.state._prev_range_high = prev_range_high
        self.state._prev_range_low = prev_range_low

        # Update delta
        side = trade.side
        if side is None:
            # Infer from price
            if self.state.best_bid and self.state.best_ask:
                if trade.price >= self.state.best_ask:
                    side = "buy"
                elif trade.price <= self.state.best_bid:
                    side = "sell"

        # Convert Side enum to string if needed
        if hasattr(side, 'value'):
            side = side.value

        if side == "buy":
            self.state.buy_volume += trade.size
        elif side == "sell":
            self.state.sell_volume += trade.size

        # Prune old delta
        cutoff = current_time - self.delta_window
        self.delta_trades.append((current_time, side, trade.size))

        while self.delta_trades and self.delta_trades[0][0] < cutoff:
            _, old_side, old_size = self.delta_trades.popleft()
            if hasattr(old_side, 'value'):
                old_side = old_side.value
            if old_side == "buy":
                self.state.buy_volume -= old_size
            elif old_side == "sell":
                self.state.sell_volume -= old_size

        self.state.delta = self.state.buy_volume - self.state.sell_volume

    def detect_buy_sweep(
        self,
        current_time: datetime,
        sweep_window_s: int,
        min_notional: float,
        depth_drop_pct: float,
    ) -> bool:
        """Detect buy-side liquidity sweep."""
        # Check if trade broke above PREVIOUS range high
        if not self.state.range_trades:
            return False

        recent_price = self.state.range_trades[-1][1]
        prev_range_high = getattr(self.state, '_prev_range_high', self.state.range_high)

        # Sweep occurs when price breaks above previous range high
        if recent_price <= prev_range_high:
            return False

        # Use delta as proxy for aggressive volume
        if self.state.best_ask is None:
            return False
        if self.state.delta * self.state.best_ask < min_notional:
            return False

        # Check ask depth dropped
        if self.state.prev_ask_depth > 0:
            depth_drop = 1 - (self.state.ask_depth / self.state.prev_ask_depth)
            if depth_drop < depth_drop_pct:
                return False

        print(f"  BUY SWEEP DETECTED at {recent_price:.2f} (prev_range_high={prev_range_high:.2f})")
        self.state.last_sweep_high = recent_price
        self.state.last_sweep_time = current_time
        self.state.last_sweep_side = "buy"
        return True

    def detect_sell_sweep(
        self,
        current_time: datetime,
        sweep_window_s: int,
        min_notional: float,
        depth_drop_pct: float,
    ) -> bool:
        """Detect sell-side liquidity sweep."""
        if not self.state.range_trades:
            return False

        recent_price = self.state.range_trades[-1][1]
        prev_range_low = getattr(self.state, '_prev_range_low', self.state.range_low)

        # Sweep occurs when price breaks below previous range low
        if recent_price >= prev_range_low:
            return False

        # Check aggressive sell volume
        if self.state.best_bid is None:
            return False
        if abs(self.state.delta) * self.state.best_bid < min_notional:
            return False

        # Check bid depth dropped
        if self.state.prev_bid_depth > 0:
            depth_drop = 1 - (self.state.bid_depth / self.state.prev_bid_depth)
            if depth_drop < depth_drop_pct:
                return False

        print(f"  SELL SWEEP DETECTED at {recent_price:.2f} (prev_range_low={prev_range_low:.2f})")
        self.state.last_sweep_low = recent_price
        self.state.last_sweep_time = current_time
        self.state.last_sweep_side = "sell"
        return True

    def check_absorption(
        self,
        current_time: datetime,
        absorption_window_s: int,
        delta_abs_min_notional: float,
    ) -> bool:
        """Check if absorption occurred after sweep."""
        if self.state.last_sweep_time is None:
            return False

        elapsed = (current_time - self.state.last_sweep_time).total_seconds()
        if elapsed > absorption_window_s:
            return False

        # Check large delta in sweep direction (using notional for consistency)
        price = self.state.best_bid or self.state.best_ask
        if price is None:
            return False
        if abs(self.state.delta) * price < delta_abs_min_notional:
            return False

        # Check price returned inside range
        if not self.state.range_trades:
            return False

        current_price = self.state.range_trades[-1][1]

        if self.state.last_sweep_side == "buy":
            # Buy sweep: price should be below sweep high
            if current_price >= self.state.last_sweep_high:
                return False
        elif self.state.last_sweep_side == "sell":
            # Sell sweep: price should be above sweep low
            if current_price <= self.state.last_sweep_low:
                return False

        print(f"  ABSORPTION DETECTED! side={self.state.last_sweep_side}, elapsed={elapsed:.1f}s, delta={self.state.delta:.1f}")
        self.state.in_absorption = True
        self.state.absorption_start = current_time
        return True

    def check_retest_entry(
        self,
        current_time: datetime,
        current_price: float,
        tick_size: float,
        retest_ticks: int,
        imb_threshold: float,
    ) -> tuple[bool, str]:
        """Check if retest conditions are met for entry.

        Returns:
            (should_enter, direction) where direction is "long" or "short"
        """
        if not self.state.in_absorption:
            return False, ""

        if self.state.last_sweep_side == "buy":
            # Look for short entry near retest of sweep high
            if self.state.last_sweep_high is None:
                return False, ""

            retest_zone = self.state.last_sweep_high - retest_ticks * tick_size

            if current_price >= retest_zone:
                # Check imbalance flipped negative
                if self.state.imbalance <= -imb_threshold and self.state.delta < 0:
                    return True, "short"

        elif self.state.last_sweep_side == "sell":
            # Look for long entry near retest of sweep low
            if self.state.last_sweep_low is None:
                return False, ""

            retest_zone = self.state.last_sweep_low + retest_ticks * tick_size

            if current_price <= retest_zone:
                # Check imbalance flipped positive
                if self.state.imbalance >= imb_threshold and self.state.delta > 0:
                    return True, "long"

        return False, ""

    def reset_absorption(self) -> None:
        """Reset absorption state after entry or timeout."""
        self.state.in_absorption = False
        self.state.absorption_start = None
