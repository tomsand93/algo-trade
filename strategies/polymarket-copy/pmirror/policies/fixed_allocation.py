"""
Fixed Allocation Policy.

This policy allocates a fixed amount of capital to each trade,
regardless of the target's position size.
"""

from pmirror.policies.base import CopyPolicy, PolicyContext, PolicyResult


class FixedAllocationPolicy(CopyPolicy):
    """
    Allocate a fixed amount of capital per trade.

    This is the simplest policy - every trade gets the same allocation.
    It's useful for:
    - Testing and development
    - Simple dollar-cost averaging into positions
    - When you want to limit exposure to any single trade
    """

    def __init__(
        self,
        capital: float = 1000.0,
        allocation_per_trade: float = 100.0,
        commission_rate: float = 0.0,
        slippage_bps: int = 5,
        skip_insufficient_cash: bool = True,
        copy_sells: bool = True,
    ):
        """
        Initialize the fixed allocation policy.

        Args:
            capital: Total capital available
            allocation_per_trade: Fixed amount to allocate per trade
            commission_rate: Commission rate per trade
            slippage_bps: Slippage in basis points
            skip_insufficient_cash: Skip buys when insufficient cash
            copy_sells: Whether to copy sell orders (True) or only buy (False)
        """
        super().__init__(capital, commission_rate, slippage_bps)

        self.allocation_per_trade = allocation_per_trade
        self.skip_insufficient_cash = skip_insufficient_cash
        self.copy_sells = copy_sells

        self._validate_parameters()

    def _validate_parameters(self, **kwargs):
        """Validate policy parameters."""
        if self.allocation_per_trade <= 0:
            raise ValueError("allocation_per_trade must be positive")

        if self.allocation_per_trade > self.capital:
            raise ValueError("allocation_per_trade cannot exceed capital")

    def evaluate(self, ctx: PolicyContext) -> PolicyResult:
        """
        Evaluate whether to copy the target trade.

        Allocates fixed amount to every trade (subject to cash constraints).

        Args:
            ctx: Policy context

        Returns:
            PolicyResult with trade decision
        """
        target = ctx.target_trade

        # Skip sells if not configured to copy them
        if target.side == "sell" and not self.copy_sells:
            return PolicyResult.skip("Not configured to copy sell orders")

        trade_size = self.allocation_per_trade

        # For buys, check cash constraint
        if target.side == "buy":
            if trade_size > ctx.current_state.cash:
                if self.skip_insufficient_cash:
                    return PolicyResult.skip(
                        f"Insufficient cash: need ${trade_size:.2f}, "
                        f"have ${ctx.current_state.cash:.2f}"
                    )
                # Otherwise, use available cash
                trade_size = ctx.current_state.cash

                if trade_size < 1.0:  # Minimum threshold
                    return PolicyResult.skip(
                        f"Available cash ${trade_size:.2f} below minimum"
                    )

        # Apply slippage to price
        adjusted_price = self._apply_slippage(target.price, target.side)

        return PolicyResult.trade(
            side=target.side,
            size=trade_size,
            price=adjusted_price,
            reason=f"Fixed allocation: ${trade_size:.2f} per trade",
        )

    def _apply_slippage(self, price: float, side: str) -> float:
        """Apply slippage to price."""
        if self.slippage_bps == 0:
            return price

        slippage_decimal = self.slippage_bps / 10000.0

        if side == "buy":
            return price * (1 + slippage_decimal)
        else:
            return price * (1 - slippage_decimal)

    def get_state(self) -> dict:
        """Get policy state."""
        state = super().get_state()
        state.update({
            "allocation_per_trade": self.allocation_per_trade,
            "skip_insufficient_cash": self.skip_insufficient_cash,
            "copy_sells": self.copy_sells,
        })
        return state

    @property
    def max_trades(self) -> int:
        """Maximum number of trades possible with current capital."""
        if self.allocation_per_trade <= 0:
            return 0
        return int(self.capital / self.allocation_per_trade)
