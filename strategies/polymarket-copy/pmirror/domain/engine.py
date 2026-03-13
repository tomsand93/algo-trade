"""
Backtest engine for copy-trade simulation.

The BacktestEngine orchestrates the simulation by:
1. Iterating through target trades in timestamp order
2. Evaluating policy decisions via PolicyContext
3. Executing trades and updating BacktestState
4. Tracking metrics and returning BacktestResult
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from pmirror.domain import Trade, Market, BacktestState, ExecutedTrade, Position
from pmirror.policies.base import CopyPolicy, PolicyContext


@dataclass
class BacktestResult:
    """
    Result of a backtest simulation.

    Contains the final state after running the backtest along
    with summary statistics.
    """

    initial_cash: float
    final_cash: float
    total_return: float
    executed_trades: list[ExecutedTrade]
    skipped_trades: int
    timestamps: list[datetime]

    @property
    def total_trades(self) -> int:
        """Total number of trades processed."""
        return len(self.executed_trades) + self.skipped_trades

    @property
    def execution_rate(self) -> float:
        """Percentage of target trades that were executed."""
        if self.total_trades == 0:
            return 0.0
        return len(self.executed_trades) / self.total_trades


class BacktestEngine:
    """
    Engine for running copy-trade backtests.

    The backtest simulates following a target wallet's trades using
    a given copy policy. It tracks cash, positions, and trade history.
    """

    def __init__(
        self,
        initial_cash: float = 10000.0,
        commission_rate: float = 0.0,
        slippage_bps: int = 0,
    ):
        """
        Initialize the backtest engine.

        Args:
            initial_cash: Starting cash in USDC
            commission_rate: Commission rate per trade (0.0 = none, 0.01 = 1%)
            slippage_bps: Slippage in basis points (1 bp = 0.01%)
        """
        self.initial_cash = initial_cash
        self.commission_rate = commission_rate
        self.slippage_bps = slippage_bps

    def run(
        self,
        target_trades: list[Trade],
        markets: dict[str, Market],
        policy: CopyPolicy,
    ) -> BacktestResult:
        """
        Run the backtest simulation.

        Args:
            target_trades: List of trades made by the target wallet
            markets: Dictionary mapping market_id to Market metadata
            policy: CopyPolicy instance that decides when/how to trade

        Returns:
            BacktestResult with final state and statistics
        """
        # Initialize state
        state = BacktestState(
            cash=self.initial_cash,
            positions={},
            trade_log=[],
            timestamps=[],
            starting_cash=self.initial_cash,
        )

        skipped = 0
        trade_history: list[Trade] = []

        # Sort trades by timestamp
        sorted_trades = sorted(target_trades, key=lambda t: t.timestamp)

        for trade in sorted_trades:
            # Add to history for policy context
            trade_history.append(trade)

            # Check if market exists
            market = markets.get(trade.market_id)
            if not market:
                skipped += 1
                continue

            # Get execution price with slippage applied
            execution_price = self._apply_slippage(trade.price, trade.side)

            # Build policy context
            ctx = PolicyContext(
                target_trade=trade,
                current_state=state,
                target_trade_history=trade_history.copy(),
                capital=self.initial_cash,
                commission_rate=self.commission_rate,
                slippage_bps=self.slippage_bps,
                current_price=execution_price,
            )

            # Evaluate policy
            result = policy.evaluate(ctx)

            if result.should_trade:
                # Check if we have enough cash for buys
                if result.side == "buy":
                    required = result.size * result.price
                    commission = required * self.commission_rate
                    if state.cash < required + commission:
                        # Not enough cash - skip
                        skipped += 1
                        continue

                # Execute the trade
                executed = self._execute_trade(
                    state=state,
                    target_trade=trade,
                    market_id=trade.market_id,
                    outcome=trade.outcome,
                    side=result.side,
                    price=result.price,
                    size=result.size,
                    reason=result.reason,
                )
                state.trade_log.append(executed)
                state.timestamps.append(trade.timestamp)
            else:
                skipped += 1

        # Calculate return
        total_return = (state.cash - self.initial_cash) / self.initial_cash

        return BacktestResult(
            initial_cash=self.initial_cash,
            final_cash=state.cash,
            total_return=total_return,
            executed_trades=state.trade_log,
            skipped_trades=skipped,
            timestamps=state.timestamps,
        )

    def _apply_slippage(self, price: float, side: str) -> float:
        """
        Apply slippage to execution price.

        For buys, we pay more (worse price).
        For sells, we receive less (worse price).

        Args:
            price: Original price
            side: "buy" or "sell"

        Returns:
            Price with slippage applied
        """
        if self.slippage_bps == 0:
            return price

        slippage_decimal = self.slippage_bps / 10000.0

        if side == "buy":
            return price * (1 + slippage_decimal)
        else:  # sell
            return price * (1 - slippage_decimal)

    def _execute_trade(
        self,
        state: BacktestState,
        target_trade: Trade,
        market_id: str,
        outcome: str,
        side: str,
        price: float,
        size: float,
        reason: str,
    ) -> ExecutedTrade:
        """
        Execute a trade and update backtest state.

        Args:
            state: Current backtest state (will be mutated)
            target_trade: The target trade that triggered this
            market_id: Market condition ID
            outcome: Outcome being traded
            side: "buy" or "sell"
            price: Execution price
            size: Trade size in USDC
            reason: Reason for the trade

        Returns:
            ExecutedTrade record
        """
        # Calculate cost/proceeds
        cost = size * price
        commission = cost * self.commission_rate

        if side == "buy":
            # Buying: subtract cost + commission from cash
            state.cash -= (cost + commission)
        else:  # sell
            # Selling: add proceeds - commission to cash
            state.cash += (cost - commission)

        # Update or create position
        position_key = f"{market_id}:{outcome}"

        if position_key in state.positions:
            # Update existing position
            existing = state.positions[position_key]
            if side == "buy":
                new_size = existing.size + cost
                new_avg_price = ((existing.avg_price * existing.shares) + (price * (size / price))) / (existing.shares + (size / price))
            else:  # sell
                new_size = existing.size - cost
                new_avg_price = existing.avg_price

            if abs(new_size) < 0.01:
                # Close position
                del state.positions[position_key]
            else:
                # Update position
                state.positions[position_key] = Position(
                    wallet="follower",
                    market_id=market_id,
                    outcome=outcome,
                    size=new_size,
                    avg_price=new_avg_price,
                    shares=abs(new_size / new_avg_price) if new_avg_price > 0 else 0,
                )
        else:
            # Create new position (only for buys)
            if side == "buy":
                shares = size / price if price > 0 else 0
                state.positions[position_key] = Position(
                    wallet="follower",
                    market_id=market_id,
                    outcome=outcome,
                    size=cost,
                    avg_price=price,
                    shares=shares,
                )

        shares = size / price if price > 0 else 0

        return ExecutedTrade(
            timestamp=target_trade.timestamp,
            market_id=market_id,
            side=side,
            price=price,
            size=size,
            shares=shares,
            slippage_bps=float(self.slippage_bps),
            fee=commission,
            target_trade_hash=target_trade.transaction_hash,
            reason=reason,
        )
