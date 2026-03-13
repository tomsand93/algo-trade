"""
Core backtest engine for copy-trading strategies.

The BacktestEngine processes target wallet trades chronologically,
applies a copy policy to generate our trades, and tracks the resulting
portfolio state over time.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from pmirror.domain import Trade, BacktestState, ExecutedTrade, Position
from pmirror.policies.base import CopyPolicy, PolicyContext, PolicyResult
from pmirror.policies.mirror_latency import MirrorLatencyPolicy


@dataclass
class BacktestConfig:
    """Configuration for a backtest."""

    # Target wallet to follow
    target_wallet: str

    # Starting capital
    capital: float = 1000.0

    # Date range
    start_date: datetime | None = None
    end_date: datetime | None = None

    # Policy to use for copying
    policy: CopyPolicy | None = None

    # Trading parameters
    commission_rate: float = 0.0
    slippage_bps: int = 5

    # Policy-specific parameters
    scale_factor: float = 0.1
    latency_seconds: int = 60

    # Data loading function
    trade_loader: Callable[[str, datetime, datetime], list[Trade]] | None = None

    def __post_init__(self):
        """Create default policy if not provided."""
        if self.policy is None:
            self.policy = MirrorLatencyPolicy(
                capital=self.capital,
                scale_factor=self.scale_factor,
                latency_seconds=self.latency_seconds,
                commission_rate=self.commission_rate,
                slippage_bps=self.slippage_bps,
            )


@dataclass
class BacktestResult:
    """Result of a backtest run."""

    # Final state
    final_state: BacktestState

    # All trades executed
    executed_trades: list[ExecutedTrade] = field(default_factory=list)

    # Target trades that were skipped
    skipped_trades: list[Trade] = field(default_factory=list)

    # Configuration used
    config: BacktestConfig | None = None

    # Performance metrics (computed separately)
    metrics: dict = field(default_factory=dict)

    # Execution metadata
    start_time: datetime | None = None
    end_time: datetime | None = None
    processing_time_ms: float = 0.0

    @property
    def total_return(self) -> float:
        """Total return as a decimal."""
        return self.final_state.total_return

    @property
    def total_trades(self) -> int:
        """Number of trades executed."""
        return len(self.executed_trades)

    @property
    def skipped_count(self) -> int:
        """Number of target trades skipped."""
        return len(self.skipped_trades)

    @property
    def skip_rate(self) -> float:
        """Percentage of target trades skipped."""
        total = self.total_trades + self.skipped_count
        if total == 0:
            return 0.0
        return self.skipped_count / total


class BacktestEngine:
    """
    Core backtesting engine.

    Processes target wallet trades and simulates following them
    according to a copy policy.
    """

    def __init__(self, config: BacktestConfig):
        """
        Initialize the backtest engine.

        Args:
            config: Backtest configuration
        """
        self.config = config
        self.policy = config.policy
        self.state = BacktestState(
            cash=config.capital,
            starting_cash=config.capital,
        )
        self.executed_trades: list[ExecutedTrade] = []
        self.skipped_trades: list[Trade] = []

    def run(self, target_trades: list[Trade]) -> BacktestResult:
        """
        Run the backtest on a list of target trades.

        Args:
            target_trades: List of trades made by the target wallet

        Returns:
            BacktestResult with final state and trade history
        """
        import time
        start_time = time.time()

        # Filter by date range if specified
        if self.config.start_date or self.config.end_date:
            target_trades = self._filter_by_date_range(target_trades)

        # Sort by timestamp to ensure chronological processing
        target_trades = sorted(target_trades, key=lambda t: t.timestamp)

        # Track trade history for context
        trade_history: list[Trade] = []

        for i, target_trade in enumerate(target_trades):
            # Add to history
            trade_history.append(target_trade)

            # Create policy context
            ctx = PolicyContext(
                target_trade=target_trade,
                current_state=self.state,
                target_trade_history=trade_history,
                capital=self.config.capital,
                commission_rate=self.config.commission_rate,
                slippage_bps=self.config.slippage_bps,
            )

            # Get policy decision
            result = self.policy.evaluate(ctx)

            if result.should_trade:
                self._execute_trade(result, target_trade)
            else:
                self.skipped_trades.append(target_trade)

        end_time = time.time()

        return BacktestResult(
            final_state=self.state,
            executed_trades=self.executed_trades,
            skipped_trades=self.skipped_trades,
            config=self.config,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            processing_time_ms=(end_time - start_time) * 1000,
        )

    def _execute_trade(self, result: PolicyResult, target_trade: Trade) -> None:
        """
        Execute a trade based on policy result.

        Args:
            result: Policy result with trade parameters
            target_trade: The target trade that triggered this
        """
        # Calculate shares
        shares = result.size / result.price if result.price > 0 else 0

        # Calculate fee
        fee = result.size * self.config.commission_rate

        # Create executed trade record
        executed = ExecutedTrade(
            timestamp=target_trade.timestamp,  # In backtest, we assume same timestamp
            market_id=target_trade.market_id,
            side=result.side,
            price=result.price,
            size=result.size,
            shares=shares,
            slippage_bps=float(self.config.slippage_bps),
            fee=fee,
            target_trade_hash=target_trade.transaction_hash,
            reason=result.reason,
        )

        self.executed_trades.append(executed)

        # Update state
        self._update_state(executed)

    def _update_state(self, trade: ExecutedTrade) -> None:
        """
        Update backtest state after executing a trade.

        Args:
            trade: The executed trade
        """
        # Calculate size delta (positive for buy, negative for sell)
        size_delta = trade.size if trade.side == "buy" else -trade.size

        # Update cash
        cost = trade.size + trade.fee
        if trade.side == "buy":
            self.state.cash -= cost
        else:  # sell
            self.state.cash += trade.size - trade.fee

        # Update position
        self.state.update_position(
            market_id=trade.market_id,
            outcome="yes",  # Simplified - assume binary markets for now
            size_delta=size_delta,
            price=trade.price,
        )

        # Record timestamp
        self.state.timestamps.append(trade.timestamp)

    def _filter_by_date_range(self, trades: list[Trade]) -> list[Trade]:
        """
        Filter trades by configured date range.

        Args:
            trades: List of trades to filter

        Returns:
            Filtered list of trades
        """
        result = trades

        if self.config.start_date:
            result = [t for t in result if t.timestamp >= self.config.start_date]

        if self.config.end_date:
            result = [t for t in result if t.timestamp < self.config.end_date]

        return result

    def reset(self) -> None:
        """Reset the engine to initial state."""
        self.state = BacktestState(
            cash=self.config.capital,
            starting_cash=self.config.capital,
        )
        self.executed_trades = []
        self.skipped_trades = []


def run_simple_backtest(
    target_wallet: str,
    trades: list[Trade],
    capital: float = 1000.0,
    scale_factor: float = 0.1,
    commission_rate: float = 0.0,
    slippage_bps: int = 5,
) -> BacktestResult:
    """
    Convenience function to run a simple backtest.

    Args:
        target_wallet: Wallet address to follow
        trades: List of target wallet trades
        capital: Starting capital
        scale_factor: Position scaling factor
        commission_rate: Commission rate
        slippage_bps: Slippage in basis points

    Returns:
        BacktestResult
    """
    config = BacktestConfig(
        target_wallet=target_wallet,
        capital=capital,
        scale_factor=scale_factor,
        commission_rate=commission_rate,
        slippage_bps=slippage_bps,
    )

    engine = BacktestEngine(config)
    return engine.run(trades)
