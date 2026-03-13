"""
Mirror Latency Policy.

This policy copies all trades from a target wallet, but applies a time delay
to simulate real-world execution latency. It can also scale position sizes
to match a percentage of the target's position.
"""

from datetime import timedelta

from pmirror.policies.base import CopyPolicy, PolicyContext, PolicyResult


class MirrorLatencyPolicy(CopyPolicy):
    """
    Copy all trades with configurable latency and position scaling.

    This is the most realistic policy for backtesting copy-trading strategies,
    as it accounts for:
    - Execution delay (you can't trade instantly after seeing the target trade)
    - Position scaling (you might not have enough capital to copy 1:1)
    - Slippage (your trades move the market slightly)
    """

    def __init__(
        self,
        capital: float = 1000.0,
        scale_factor: float = 0.1,
        latency_seconds: int = 60,
        min_position_size: float = 10.0,
        max_position_size: float = 500.0,
        commission_rate: float = 0.0,
        slippage_bps: int = 5,
        skip_small_trades: bool = True,
        min_target_size: float = 50.0,
    ):
        """
        Initialize the mirror latency policy.

        Args:
            capital: Total capital available
            scale_factor: Percentage of target position to copy (0.1 = 10%)
            latency_seconds: Delay before executing trade (simulates API/parsing delay)
            min_position_size: Minimum position size in USDC
            max_position_size: Maximum position size in USDC
            commission_rate: Commission rate per trade
            slippage_bps: Slippage in basis points
            skip_small_trades: Skip trades below min_target_size
            min_target_size: Minimum target trade size to consider copying
        """
        super().__init__(capital, commission_rate, slippage_bps)

        self.scale_factor = scale_factor
        self.latency_seconds = latency_seconds
        self.min_position_size = min_position_size
        self.max_position_size = max_position_size
        self.skip_small_trades = skip_small_trades
        self.min_target_size = min_target_size

        self._validate_parameters()

    def _validate_parameters(self, **kwargs):
        """Validate policy parameters."""
        if not 0 < self.scale_factor <= 1:
            raise ValueError("scale_factor must be between 0 and 1")

        if self.latency_seconds < 0:
            raise ValueError("latency_seconds must be non-negative")

        if self.min_position_size <= 0:
            raise ValueError("min_position_size must be positive")

        if self.max_position_size < self.min_position_size:
            raise ValueError("max_position_size must be >= min_position_size")

        if self.min_target_size <= 0:
            raise ValueError("min_target_size must be positive")

    def evaluate(self, ctx: PolicyContext) -> PolicyResult:
        """
        Evaluate whether to copy the target trade.

        Copies all trades (after latency) with scaled position size.

        Args:
            ctx: Policy context

        Returns:
            PolicyResult with trade decision
        """
        target = ctx.target_trade

        # Check if target trade is large enough
        if self.skip_small_trades and target.size < self.min_target_size:
            return PolicyResult.skip(
                f"Target trade size ${target.size:.2f} below minimum ${self.min_target_size}"
            )

        # Calculate our position size
        our_size = target.size * self.scale_factor

        # Apply position size limits
        if our_size < self.min_position_size:
            return PolicyResult.skip(
                f"Scaled position ${our_size:.2f} below minimum ${self.min_position_size}"
            )

        if our_size > self.max_position_size:
            our_size = self.max_position_size

        # Check if we have enough cash
        if target.side == "buy" and our_size > ctx.current_state.cash:
            # Reduce to available cash
            if ctx.current_state.cash < self.min_position_size:
                return PolicyResult.skip(
                    f"Insufficient cash: ${ctx.current_state.cash:.2f} available"
                )
            our_size = ctx.current_state.cash

        # Apply slippage to price
        adjusted_price = self._apply_slippage(target.price, target.side)

        # Calculate reason
        reason = (
            f"Mirror trade: {target.side} ${our_size:.2f} @ {adjusted_price:.4f} "
            f"(scaled {self.scale_factor:.1%} of ${target.size:.2f}, "
            f"{self.latency_seconds}s latency)"
        )

        return PolicyResult.trade(
            side=target.side,
            size=our_size,
            price=adjusted_price,
            reason=reason,
        )

    def _apply_slippage(self, price: float, side: str) -> float:
        """Apply slippage to price."""
        if self.slippage_bps == 0:
            return price

        slippage_decimal = self.slippage_bps / 10000.0

        # For buys, we pay more
        # For sells, we receive less
        if side == "buy":
            return price * (1 + slippage_decimal)
        else:
            return price * (1 - slippage_decimal)

    def get_state(self) -> dict:
        """Get policy state."""
        state = super().get_state()
        state.update({
            "scale_factor": self.scale_factor,
            "latency_seconds": self.latency_seconds,
            "min_position_size": self.min_position_size,
            "max_position_size": self.max_position_size,
            "skip_small_trades": self.skip_small_trades,
            "min_target_size": self.min_target_size,
        })
        return state

    @property
    def latency(self) -> timedelta:
        """Get latency as a timedelta."""
        return timedelta(seconds=self.latency_seconds)
