"""Core orderbook trading strategy."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .config import Config
from .distribution import ConditionalDist, compute_horizon_return
from .indicators import IndicatorEngine


class PositionSide(Enum):
    """Position side."""
    LONG = "long"
    SHORT = "short"


@dataclass
class Signal:
    """Trading signal."""
    timestamp: datetime
    direction: str  # "long" or "short"
    entry_price: float
    stop_price: float
    tp1_price: float
    tp2_price: float
    quantity: float
    p_up: float
    p_down: float
    state_key: str
    dist_samples: int
    reason: str


@dataclass
class Position:
    """Open position."""
    side: PositionSide
    entry_price: float
    quantity: float
    entry_time: datetime
    stop_price: float
    tp1_price: float
    tp2_price: float
    tp1_filled: bool = False
    p_up: float = 0.0
    p_down: float = 0.0
    state_key: str = ""
    dist_samples: int = 0

    @property
    def is_closed(self) -> bool:
        """Check if position is fully closed."""
        return self.quantity == 0


@dataclass
class TradeRecord:
    """Completed trade record."""
    entry_time: datetime
    exit_time: datetime
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    fees: float
    slippage: float
    reason: str
    p_up: float
    p_down: float
    state_key: str
    dist_samples: int


class OrderbookStrategy:
    """Orderbook L2 trading strategy with probability gating."""

    def __init__(self, config: Config):
        self.config = config
        self.indicators = IndicatorEngine(
            range_window_s=config.range_window_s,
            depth_levels=config.depth_levels,
        )
        self.distribution = ConditionalDist(
            dist_type=config.dist_type,
            sigma_floor=config.sigma_floor,
            min_samples=config.min_dist_samples,
            use_conditioning=config.use_state_conditioning,
            lookback=config.dist_lookback,
            hist_bins=config.hist_bins,
        )

        # Position tracking
        self.position: Position | None = None
        self.trades: list[TradeRecord] = []

        # Horizon tracking (for distribution updates)
        self.pending_horizons: list[dict] = []  # (end_time, start_mid, state_key)
        self._last_horizon_schedule_time: datetime | None = None
        self._horizon_schedule_interval_s: float = config.horizon_s  # Schedule at horizon interval

    def on_event(
        self,
        event,
        current_time: datetime,
        current_mid: float,
    ) -> Signal | None:
        """Process event and generate signal if conditions met."""
        # First, update horizons (no peeking - these were scheduled earlier)
        self._update_horizons(current_time, current_mid)

        # Then process the event
        if hasattr(event, "bids"):  # BookSnapshot
            self.indicators.on_book_snapshot(event, current_time)
        elif hasattr(event, "price"):  # Trade
            self.indicators.on_trade(event, current_time, current_mid)

            # Check for sweep patterns on trade events
            if not self.indicators.state.in_absorption:
                # Try to detect buy sweep
                if self.indicators.detect_buy_sweep(
                    current_time=current_time,
                    sweep_window_s=self.config.sweep_window_s,
                    min_notional=self.config.sweep_min_notional,
                    depth_drop_pct=self.config.depth_drop_pct,
                ):
                    pass  # Sweep detected, state updated
                # Try to detect sell sweep
                elif self.indicators.detect_sell_sweep(
                    current_time=current_time,
                    sweep_window_s=self.config.sweep_window_s,
                    min_notional=self.config.sweep_min_notional,
                    depth_drop_pct=self.config.depth_drop_pct,
                ):
                    pass  # Sweep detected, state updated

            # Always check for absorption (can trigger after sweep OR confirm existing)
            if self.indicators.state.last_sweep_time is not None:
                self.indicators.check_absorption(
                    current_time=current_time,
                    absorption_window_s=self.config.absorption_window_s,
                    delta_abs_min_notional=self.config.delta_abs_min_notional,
                )

        # Schedule horizon returns periodically to build distribution samples
        # This fixes the chicken-and-egg problem where we need samples to enter,
        # but can only get samples by entering. Now we learn from ALL market states.
        self._maybe_schedule_horizon(current_time, current_mid)

        # Check for exits first
        exit_signal = self._check_exits(current_time, current_mid)
        if exit_signal is not None:
            return exit_signal

        # Then check for entries
        return self._check_entries(current_time, current_mid)

    def _update_horizons(self, current_time: datetime, current_mid: float) -> None:
        """Update distribution with completed horizons."""
        still_pending = []

        for h in self.pending_horizons:
            if current_time >= h["end_time"]:
                # Horizon complete - compute return and update distribution
                ret = compute_horizon_return(h["start_mid"], current_mid)
                self.distribution.update(ret, h["state_key"])
            else:
                still_pending.append(h)

        self.pending_horizons = still_pending

    def _schedule_horizon(self, current_time: datetime, current_mid: float) -> None:
        """Schedule a horizon return for future update."""
        end_time = current_time + timedelta(seconds=self.config.horizon_s)
        state_key = self.distribution.get_state_key(
            self.indicators.state.imbalance,
            self.indicators.state.delta,
        )

        self.pending_horizons.append({
            "end_time": end_time,
            "start_mid": current_mid,
            "state_key": state_key,
        })

    def _maybe_schedule_horizon(self, current_time: datetime, current_mid: float) -> None:
        """Schedule horizon returns periodically to build distribution samples.

        This fixes the chicken-and-egg problem: we need distribution samples to enter trades,
        but previously we only scheduled horizons on entry. Now we schedule horizons from
        all market states so the distribution can learn before we enter.
        """
        # Schedule if enough time has passed since last schedule
        if self._last_horizon_schedule_time is None:
            should_schedule = True
        else:
            elapsed = (current_time - self._last_horizon_schedule_time).total_seconds()
            should_schedule = elapsed >= self._horizon_schedule_interval_s

        if should_schedule:
            self._schedule_horizon(current_time, current_mid)
            self._last_horizon_schedule_time = current_time

    def _check_entries(
        self, current_time: datetime, current_mid: float
    ) -> Signal | None:
        """Check for entry conditions."""
        if self.position is not None:
            return None

        # Debug: log state periodically
        state = self.indicators.state
        if state.last_sweep_high is not None or state.last_sweep_low is not None:
            print(f"DEBUG: mid={current_mid:.2f}, range_hi={state.range_high:.2f}, range_lo={state.range_low:.2f}, "
                  f"sweep_hi={state.last_sweep_high}, sweep_lo={state.last_sweep_low}, "
                  f"imb={state.imbalance:.3f}, delta={state.delta:.1f}, "
                  f"in_absorption={state.in_absorption}")

        # Check retest entry
        should_enter, direction = self.indicators.check_retest_entry(
            current_time=current_time,
            current_price=current_mid,
            tick_size=self.config.tick_size,
            retest_ticks=self.config.retest_ticks,
            imb_threshold=self.config.imb_threshold,
        )

        if not should_enter:
            return None

        print(f"DEBUG: Entry signal detected! direction={direction}")

        # Get probability gate
        p_up, p_down, state_key, n_samples = self.distribution.get_probabilities(
            self.indicators.state.imbalance,
            self.indicators.state.delta,
        )

        print(f"DEBUG: p_up={p_up:.3f}, p_down={p_down:.3f}, n_samples={n_samples}")

        # Check minimum samples
        if n_samples < self.config.min_dist_samples:
            print(f"DEBUG: Not enough samples ({n_samples} < {self.config.min_dist_samples})")
            return None

        # Probability gate - require both threshold AND directional advantage
        if direction == "long":
            if p_up < self.config.p_threshold:
                print(f"DEBUG: p_up {p_up:.3f} < threshold {self.config.p_threshold}")
                return None
            if p_up <= p_down:
                print(f"DEBUG: p_up {p_up:.3f} <= p_down {p_down:.3f} - no edge")
                return None
        else:  # short
            if p_down < self.config.p_threshold:
                print(f"DEBUG: p_down {p_down:.3f} < threshold {self.config.p_threshold}")
                return None
            if p_down <= p_up:
                print(f"DEBUG: p_down {p_down:.3f} <= p_up {p_up:.3f} - no edge")
                return None

        # Compute position sizing
        qty = self._compute_quantity(p_up if direction == "long" else p_down)

        # Compute prices
        state = self.indicators.state
        if direction == "long":
            entry_price = current_mid
            # Stop is BELOW entry for long position
            stop_price = entry_price - self.config.stop_ticks * self.config.tick_size
            tp1_price = (state.range_high + state.range_low) / 2
            tp2_price = state.range_high
        else:
            entry_price = current_mid
            # Stop is ABOVE entry for short position
            stop_price = entry_price + self.config.stop_ticks * self.config.tick_size
            tp1_price = (state.range_high + state.range_low) / 2
            tp2_price = state.range_low

        signal = Signal(
            timestamp=current_time,
            direction=direction,
            entry_price=entry_price,
            stop_price=stop_price,
            tp1_price=tp1_price,
            tp2_price=tp2_price,
            quantity=qty,
            p_up=p_up,
            p_down=p_down,
            state_key=state_key,
            dist_samples=n_samples,
            reason=f"{direction.upper()}_ENTRY",
        )

        # Schedule horizon return
        self._schedule_horizon(current_time, current_mid)

        return signal

    def _compute_quantity(self, p_edge: float) -> float:
        """Compute position quantity based on probability edge."""
        if not self.config.use_prob_sizing:
            return self.config.base_qty

        # Edge is distance from 0.5
        edge = abs(p_edge - 0.5) * 2  # 0 to 1

        # Scale base quantity
        mult = edge / self.config.edge_ref if self.config.edge_ref > 0 else 1
        mult = min(max(mult, 0), self.config.max_mult)

        return self.config.base_qty * mult

    def _check_exits(
        self, current_time: datetime, current_mid: float
    ) -> Signal | None:
        """Check for exit conditions on open position."""
        if self.position is None:
            return None

        pos = self.position
        elapsed = (current_time - pos.entry_time).total_seconds()

        # Time stop
        if elapsed > self.config.time_stop_s:
            return self._create_exit_signal(current_time, current_mid, "TIME_STOP")

        # Stop loss
        if pos.side == PositionSide.LONG:
            if current_mid <= pos.stop_price:
                return self._create_exit_signal(current_time, current_mid, "STOP_LOSS")
            # TP1 (close 50%)
            if not pos.tp1_filled and current_mid >= pos.tp1_price:
                pos.tp1_filled = True
                return self._create_exit_signal(
                    current_time, current_mid, "TP1", partial=0.5
                )
            # TP2 (close remaining)
            if current_mid >= pos.tp2_price:
                return self._create_exit_signal(current_time, current_mid, "TP2")
        else:  # SHORT
            if current_mid >= pos.stop_price:
                return self._create_exit_signal(current_time, current_mid, "STOP_LOSS")
            # TP1
            if not pos.tp1_filled and current_mid <= pos.tp1_price:
                pos.tp1_filled = True
                return self._create_exit_signal(
                    current_time, current_mid, "TP1", partial=0.5
                )
            # TP2
            if current_mid <= pos.tp2_price:
                return self._create_exit_signal(current_time, current_mid, "TP2")

        return None

    def _create_exit_signal(
        self, current_time: datetime, current_mid: float, reason: str, partial: float = 1.0
    ) -> Signal:
        """Create exit signal."""
        pos = self.position

        # Determine exit direction
        direction = "sell" if pos.side == PositionSide.LONG else "buy"

        return Signal(
            timestamp=current_time,
            direction=direction,
            entry_price=current_mid,
            stop_price=0.0,
            tp1_price=0.0,
            tp2_price=0.0,
            quantity=pos.quantity * partial,
            p_up=pos.p_up,
            p_down=pos.p_down,
            state_key="",
            dist_samples=pos.dist_samples,
            reason=reason,
        )

    def on_signal(self, signal: Signal) -> None:
        """Handle signal (entry or exit)."""
        if signal.reason.endswith("_ENTRY"):
            # Open position
            side = PositionSide.LONG if signal.direction == "long" else PositionSide.SHORT
            self.position = Position(
                side=side,
                entry_price=signal.entry_price,
                quantity=signal.quantity,
                entry_time=signal.timestamp,
                stop_price=signal.stop_price,
                tp1_price=signal.tp1_price,
                tp2_price=signal.tp2_price,
                p_up=signal.p_up,
                p_down=signal.p_down,
                state_key=signal.state_key,  # FIX: Copy state_key from signal
                dist_samples=signal.dist_samples,  # FIX: Copy dist_samples from signal
            )
            self.indicators.reset_absorption()
        else:
            # Close position (exit)
            if self.position:
                self.trades.append(TradeRecord(
                    entry_time=self.position.entry_time,
                    exit_time=signal.timestamp,
                    side=self.position.side.value,
                    entry_price=self.position.entry_price,
                    exit_price=signal.entry_price,
                    quantity=signal.quantity,
                    pnl=self._compute_pnl(self.position, signal),
                    fees=0.0,  # Computed in execution module
                    slippage=0.0,  # Computed in execution module
                    reason=signal.reason,
                    p_up=self.position.p_up,
                    p_down=self.position.p_down,
                    state_key=signal.state_key,
                    dist_samples=signal.dist_samples,
                ))

                # Update position quantity for partial exits
                self.position.quantity -= signal.quantity
                if self.position.quantity <= 0:
                    self.position = None

    def _compute_pnl(self, position: Position, signal: Signal) -> float:
        """Compute PnL for trade."""
        if position.side == PositionSide.LONG:
            return (signal.entry_price - position.entry_price) * signal.quantity
        else:
            return (position.entry_price - signal.entry_price) * signal.quantity


from datetime import timedelta  # Import at module level for use in strategy
