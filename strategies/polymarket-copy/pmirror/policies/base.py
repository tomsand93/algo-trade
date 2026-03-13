"""
Base policy class for copy-trading.

A CopyPolicy determines when and how much to trade when following a target wallet.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from pmirror.domain import Trade, BacktestState


@dataclass
class PolicyContext:
    """
    Context provided to a policy when making a decision.

    Contains all relevant information about the current state of the
    backtest and the target trade being evaluated.
    """

    # The target trade we're considering copying
    target_trade: Trade

    # Current state of our backtest (cash, positions, etc.)
    current_state: BacktestState

    # All trades made by the target wallet so far (for context)
    target_trade_history: list[Trade]

    # Settings
    capital: float
    commission_rate: float
    slippage_bps: float

    # Optional: Market data (if available)
    current_price: float | None = None
    market_liquidity: float | None = None


@dataclass
class PolicyResult:
    """
    Result of a policy decision.

    Describes what action to take in response to a target trade.
    """

    # Whether to execute a trade
    should_trade: bool

    # Trade parameters (if should_trade=True)
    side: str  # "buy" or "sell"
    size: float  # Trade size in USDC
    price: float  # Execution price

    # Reasoning for the decision (useful for debugging)
    reason: str

    # If we chose not to trade, why?
    skip_reason: str = ""

    @classmethod
    def skip(cls, reason: str) -> "PolicyResult":
        """Create a result indicating we should skip this trade."""
        return cls(
            should_trade=False,
            side="",
            size=0.0,
            price=0.0,
            reason="",
            skip_reason=reason,
        )

    @classmethod
    def trade(
        cls,
        side: str,
        size: float,
        price: float,
        reason: str = "",
    ) -> "PolicyResult":
        """Create a result indicating we should execute a trade."""
        return cls(
            should_trade=True,
            side=side,
            size=size,
            price=price,
            reason=reason,
        )


class CopyPolicy(ABC):
    """
    Abstract base class for copy-trade policies.

    Subclasses implement the `evaluate` method to determine whether
    and how much to trade when a target wallet makes a trade.
    """

    def __init__(
        self,
        capital: float = 1000.0,
        commission_rate: float = 0.0,
        slippage_bps: int = 0,
        **kwargs,
    ):
        """
        Initialize the policy.

        Args:
            capital: Total capital available for trading
            commission_rate: Commission rate per trade (0.0 = none, 0.01 = 1%)
            slippage_bps: Slippage in basis points
            **kwargs: Additional policy-specific parameters
        """
        self.capital = capital
        self.commission_rate = commission_rate
        self.slippage_bps = slippage_bps

    @abstractmethod
    def evaluate(self, ctx: PolicyContext) -> PolicyResult:
        """
        Evaluate whether to copy a target trade.

        Args:
            ctx: Policy context with target trade and current state

        Returns:
            PolicyResult with decision and trade parameters
        """
        pass

    def _validate_parameters(self, **kwargs):
        """
        Validate policy-specific parameters.

        Override in subclasses to add validation.
        """
        # Default: no validation
        pass

    def get_state(self) -> dict:
        """
        Get the current state of the policy.

        Useful for saving/loading policy state.

        Returns:
            Dictionary representation of policy state
        """
        return {
            "capital": self.capital,
            "commission_rate": self.commission_rate,
            "slippage_bps": self.slippage_bps,
        }

    def set_state(self, state: dict):
        """
        Restore policy state from a dictionary.

        Args:
            state: Dictionary from get_state()
        """
        self.capital = state.get("capital", self.capital)
        self.commission_rate = state.get("commission_rate", self.commission_rate)
        self.slippage_bps = state.get("slippage_bps", self.slippage_bps)


class SimplePolicy(CopyPolicy):
    """
    Simple policy that copies every trade with fixed position sizing.

    This is a reference implementation for testing.
    """

    def __init__(
        self,
        capital: float = 1000.0,
        position_size: float = 100.0,
        commission_rate: float = 0.0,
        slippage_bps: int = 0,
    ):
        """
        Initialize the simple policy.

        Args:
            capital: Total capital (not directly used, for context)
            position_size: Fixed size for each trade in USDC
            commission_rate: Commission rate per trade
            slippage_bps: Slippage in basis points
        """
        super().__init__(capital, commission_rate, slippage_bps)
        self.position_size = position_size

    def evaluate(self, ctx: PolicyContext) -> PolicyResult:
        """
        Copy every trade with fixed position size.

        Args:
            ctx: Policy context

        Returns:
            PolicyResult with fixed size trade
        """
        # Apply slippage to price
        adjusted_price = self._apply_slippage(
            ctx.target_trade.price,
            ctx.target_trade.side,
        )

        return PolicyResult.trade(
            side=ctx.target_trade.side,
            size=self.position_size,
            price=adjusted_price,
            reason=f"Copy all trades with fixed size ${self.position_size}",
        )

    def _apply_slippage(self, price: float, side: str) -> float:
        """Apply slippage to price."""
        if self.slippage_bps == 0:
            return price

        slippage_decimal = self.slippage_bps / 10000.0

        # For buys, we pay more (worse price)
        # For sells, we receive less (worse price)
        if side == "buy":
            return price * (1 + slippage_decimal)
        else:
            return price * (1 - slippage_decimal)

    def get_state(self) -> dict:
        """Get policy state."""
        state = super().get_state()
        state["position_size"] = self.position_size
        return state
