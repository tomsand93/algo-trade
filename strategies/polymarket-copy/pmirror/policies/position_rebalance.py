"""
Position Rebalance Policy.

This policy maintains portfolio weights similar to the target wallet.
It periodically rebalances to match target allocations.
"""

from datetime import timedelta

from pmirror.policies.base import CopyPolicy, PolicyContext, PolicyResult
from pmirror.domain import Position


class PositionRebalancePolicy(CopyPolicy):
    """
    Maintain portfolio weights similar to the target wallet.

    This policy:
    1. Tracks the target wallet's position allocations
    2. Rebalances our portfolio to match target weights
    3. Only trades when allocation drift exceeds threshold

    This is more sophisticated than simple mirroring - it captures
    the target's overall market exposure rather than individual trades.
    """

    def __init__(
        self,
        capital: float = 1000.0,
        rebalance_threshold: float = 0.05,
        rebalance_interval: str = "1h",
        min_position_size: float = 10.0,
        commission_rate: float = 0.0,
        slippage_bps: int = 5,
        max_markets: int = 10,
    ):
        """
        Initialize the position rebalance policy.

        Args:
            capital: Total capital available
            rebalance_threshold: Rebalance when weights drift by this much (0.05 = 5%)
            rebalance_interval: How often to check for rebalancing ('5m', '1h', '1d')
            min_position_size: Minimum position size in USDC
            commission_rate: Commission rate per trade
            slippage_bps: Slippage in basis points
            max_markets: Maximum number of markets to hold positions in
        """
        super().__init__(capital, commission_rate, slippage_bps)

        self.rebalance_threshold = rebalance_threshold
        self.rebalance_interval = rebalance_interval
        self.min_position_size = min_position_size
        self.max_markets = max_markets

        # Track last rebalance time
        self._last_rebalance = None

        self._validate_parameters()

    def _validate_parameters(self, **kwargs):
        """Validate policy parameters."""
        if not 0 < self.rebalance_threshold <= 1:
            raise ValueError("rebalance_threshold must be between 0 and 1")

        if self.min_position_size <= 0:
            raise ValueError("min_position_size must be positive")

        if self.max_markets < 1:
            raise ValueError("max_markets must be at least 1")

        valid_intervals = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
        if self.rebalance_interval not in valid_intervals:
            raise ValueError(f"rebalance_interval must be one of {valid_intervals}")

    def evaluate(self, ctx: PolicyContext) -> PolicyResult:
        """
        Evaluate whether to rebalance based on target trade.

        This policy doesn't directly copy trades - it uses target trades
        as a signal to check if rebalancing is needed.

        Args:
            ctx: Policy context

        Returns:
            PolicyResult with rebalancing trades
        """
        # Check if enough time has passed since last rebalance
        if self._last_rebalance is not None:
            elapsed = ctx.target_trade.timestamp - self._last_rebalance
            interval_delta = self._parse_interval(self.rebalance_interval)

            if elapsed < interval_delta:
                return PolicyResult.skip(
                    f"Rebalance interval not met ({elapsed} < {interval_delta})"
                )

        # Calculate target and current allocations
        target_allocations = self._get_target_allocations(ctx)
        current_allocations = self._get_current_allocations(ctx)

        # Check if rebalancing is needed
        drift = self._calculate_allocation_drift(target_allocations, current_allocations)

        if drift < self.rebalance_threshold:
            return PolicyResult.skip(
                f"Allocation drift {drift:.2%} below threshold {self.rebalance_threshold:.2%}"
            )

        # Find the market with largest drift
        trades = self._generate_rebalance_trades(ctx, target_allocations, current_allocations)

        if not trades:
            return PolicyResult.skip("No rebalancing trades needed")

        # Return the first trade (will be called multiple times)
        trade = trades[0]
        return PolicyResult.trade(
            side=trade["side"],
            size=trade["size"],
            price=trade["price"],
            reason=trade["reason"],
        )

    def _get_target_allocations(self, ctx: PolicyContext) -> dict[str, float]:
        """
        Calculate target wallet's allocation by market.

        Returns:
            Dict mapping market_id:outcome -> allocation fraction
        """
        allocations = {}
        total_exposure = 0.0

        # Sum up target's positions
        for trade in ctx.target_trade_history:
            key = f"{trade.market_id}:{trade.outcome}"

            if trade.side == "buy":
                allocations[key] = allocations.get(key, 0) + trade.size
            else:  # sell
                allocations[key] = allocations.get(key, 0) - trade.size

            total_exposure += trade.size

        # Convert to fractions
        if total_exposure > 0:
            for key in allocations:
                allocations[key] = abs(allocations[key]) / total_exposure

        return allocations

    def _get_current_allocations(self, ctx: PolicyContext) -> dict[str, float]:
        """
        Calculate our current allocation by market.

        Returns:
            Dict mapping market_id:outcome -> allocation fraction
        """
        allocations = {}
        total_equity = ctx.current_state.equity

        if total_equity <= 0:
            return {}

        for pos in ctx.current_state.positions.values():
            key = f"{pos.market_id}:{pos.outcome}"
            allocations[key] = abs(pos.size) / total_equity

        return allocations

    def _calculate_allocation_drift(
        self,
        target: dict[str, float],
        current: dict[str, float],
    ) -> float:
        """
        Calculate maximum allocation drift.

        Returns:
            Maximum drift across all positions
        """
        all_keys = set(target.keys()) | set(current.keys())
        max_drift = 0.0

        for key in all_keys:
            target_weight = target.get(key, 0.0)
            current_weight = current.get(key, 0.0)
            drift = abs(target_weight - current_weight)
            max_drift = max(max_drift, drift)

        return max_drift

    def _generate_rebalance_trades(
        self,
        ctx: PolicyContext,
        target_allocations: dict[str, float],
        current_allocations: dict[str, float],
    ) -> list[dict]:
        """
        Generate trades to rebalance to target allocations.

        Returns:
            List of trade dicts with side, size, price, reason
        """
        trades = []
        total_equity = ctx.current_state.equity

        # Get current price from target trade
        current_price = ctx.target_trade.price

        all_keys = set(target_allocations.keys()) | set(current_allocations.keys())

        for key in all_keys:
            target_weight = target_allocations.get(key, 0.0)
            current_weight = current_allocations.get(key, 0.0)

            # Skip if drift is small
            if abs(target_weight - current_weight) < self.rebalance_threshold:
                continue

            target_value = target_weight * total_equity
            current_value = current_weight * total_equity
            diff = target_value - current_value

            # Skip small trades
            if abs(diff) < self.min_position_size:
                continue

            if diff > 0:
                # Need to buy
                trades.append({
                    "side": "buy",
                    "size": diff,
                    "price": self._apply_slippage(current_price, "buy"),
                    "reason": f"Rebalance: buy ${diff:.2f} of {key} "
                            f"(target {target_weight:.2%}, current {current_weight:.2%})",
                })
            else:
                # Need to sell
                trades.append({
                    "side": "sell",
                    "size": abs(diff),
                    "price": self._apply_slippage(current_price, "sell"),
                    "reason": f"Rebalance: sell ${abs(diff):.2f} of {key} "
                            f"(target {target_weight:.2%}, current {current_weight:.2%})",
                })

        # Sort by size (largest trades first)
        trades.sort(key=lambda t: t["size"], reverse=True)

        # Limit number of trades
        return trades[:self.max_markets]

    def _apply_slippage(self, price: float, side: str) -> float:
        """Apply slippage to price."""
        if self.slippage_bps == 0:
            return price

        slippage_decimal = self.slippage_bps / 10000.0

        if side == "buy":
            return price * (1 + slippage_decimal)
        else:
            return price * (1 - slippage_decimal)

    def _parse_interval(self, interval: str) -> timedelta:
        """Parse interval string to timedelta."""
        mapping = {
            "1m": timedelta(minutes=1),
            "5m": timedelta(minutes=5),
            "15m": timedelta(minutes=15),
            "30m": timedelta(minutes=30),
            "1h": timedelta(hours=1),
            "4h": timedelta(hours=4),
            "1d": timedelta(days=1),
        }
        return mapping.get(interval, timedelta(hours=1))

    def get_state(self) -> dict:
        """Get policy state."""
        state = super().get_state()
        state.update({
            "rebalance_threshold": self.rebalance_threshold,
            "rebalance_interval": self.rebalance_interval,
            "min_position_size": self.min_position_size,
            "max_markets": self.max_markets,
            "last_rebalance": self._last_rebalance.isoformat() if self._last_rebalance else None,
        })
        return state

    def set_state(self, state: dict):
        """Restore policy state."""
        super().set_state(state)
        if state.get("last_rebalance"):
            from datetime import datetime
            self._last_rebalance = datetime.fromisoformat(state["last_rebalance"])
