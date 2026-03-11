"""Execution model for orderbook backtesting."""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Fill:
    """Order fill."""
    timestamp: datetime
    price: float
    quantity: float
    side: str
    fee: float
    slippage: float


class ExecutionModel:
    """Conservative execution model with latency, slippage, and fees."""

    def __init__(
        self,
        tick_size: float,
        slippage_ticks: int,
        fee_per_contract: float,
        latency_ms: int,
    ):
        self.tick_size = tick_size
        self.slippage_ticks = slippage_ticks
        self.fee_per_contract = fee_per_contract
        self.latency = timedelta(milliseconds=latency_ms)
        self.pending_signals: list = []

    def submit_signal(self, signal, current_time: datetime) -> datetime:
        """Submit signal for execution after latency."""
        execute_time = current_time + self.latency
        self.pending_signals.append({
            "signal": signal,
            "execute_time": execute_time,
        })
        return execute_time

    def try_execute(
        self,
        current_time: datetime,
        best_bid: float | None,
        best_ask: float | None,
        next_trade_price: float | None,
    ) -> Fill | None:
        """Try to execute pending signals at current time.

        Conservative fill model:
        - If next trade available, use that price ± slippage
        - Otherwise, use mid ± slippage
        """
        if not self.pending_signals:
            return None

        ready = [s for s in self.pending_signals if s["execute_time"] <= current_time]
        if not ready:
            return None

        # Execute first ready signal
        sig_info = ready[0]
        signal = sig_info["signal"]
        self.pending_signals.remove(sig_info)

        # Determine fill price with conservative slippage
        slippage = self.slippage_ticks * self.tick_size

        if next_trade_price is not None:
            base_price = next_trade_price
        elif best_bid is not None and best_ask is not None:
            base_price = (best_bid + best_ask) / 2
        else:
            return None  # Cannot determine price

        if signal.direction == "long" or signal.direction == "buy":
            fill_price = base_price + slippage
        else:
            fill_price = base_price - slippage

        # Compute fee
        fee = signal.quantity * self.fee_per_contract

        return Fill(
            timestamp=current_time,
            price=fill_price,
            quantity=signal.quantity,
            side=signal.direction,
            fee=fee,
            slippage=slippage * signal.quantity,
        )

    def has_pending(self) -> bool:
        """Check if there are pending signals."""
        return len(self.pending_signals) > 0
