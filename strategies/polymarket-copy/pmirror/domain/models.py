"""
Core domain models for the Polymarket copy-trade backtest system.

These models represent the core business entities and are independent
of any external API or storage format.
"""

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Market(BaseModel):
    """
    Represents a Polymarket prediction market.

    A market is a binary or multi-outcome event that users can trade on.
    """

    condition_id: str = Field(
        ...,
        description="Unique identifier for the market (often a CIP-10 hash)",
    )

    question: str = Field(
        ...,
        description="The question being bet on",
    )

    outcomes: list[str] = Field(
        default_factory=lambda: ["yes", "no"],
        description="Possible outcomes (e.g., ['yes', 'no'] for binary markets)",
    )

    end_time: datetime | None = Field(
        default=None,
        description="When the market closes for trading",
    )

    resolution: str | None = Field(
        default=None,
        description="The resolved outcome if the market has settled (e.g., 'yes', 'no')",
    )

    description: str | None = Field(
        default=None,
        description="Additional market description",
    )

    volume: float | None = Field(
        default=None,
        ge=0,
        description="Total trading volume in USDC",
    )

    liquidity: float | None = Field(
        default=None,
        ge=0,
        description="Current liquidity in USDC",
    )

    created_time: datetime | None = Field(
        default=None,
        description="When the market was created",
    )

    @property
    def is_binary(self) -> bool:
        """Check if this is a binary (yes/no) market."""
        return sorted(self.outcomes) == ["no", "yes"]

    @property
    def is_resolved(self) -> bool:
        """Check if the market has been resolved."""
        return self.resolution is not None

    @property
    def is_closed(self) -> bool:
        """Check if the market is closed for trading."""
        if self.end_time is None:
            return False
        # Handle both naive and aware datetimes
        now = datetime.now(timezone.utc)
        end_time = self.end_time
        if end_time.tzinfo is None:
            # Naive datetime - assume UTC for comparison (use naive now)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
        return now > end_time


class Trade(BaseModel):
    """
    Represents a single trade on Polymarket.

    Trades are the atomic unit of activity - someone buying or selling
    shares in a specific outcome of a market.
    """

    transaction_hash: str = Field(
        ...,
        description="Unique transaction hash",
    )

    timestamp: datetime = Field(
        ...,
        description="When the trade occurred",
    )

    maker: str = Field(
        ...,
        description="Wallet address of the maker (who posted the order)",
    )

    taker: str | None = Field(
        default=None,
        description="Wallet address of the taker (who filled the order)",
    )

    side: Literal["buy", "sell"] = Field(
        ...,
        description="Whether this was a buy (long) or sell (short)",
    )

    outcome: str = Field(
        ...,
        description="The outcome being traded (e.g., 'yes', 'no')",
    )

    price: float = Field(
        ...,
        ge=0,
        le=1,
        description="Price per share (0-1, represents implied probability)",
    )

    size: float = Field(
        ...,
        gt=0,
        description="Size of the trade in USDC",
    )

    market_id: str = Field(
        ...,
        description="Condition ID of the market being traded",
    )

    shares: float | None = Field(
        default=None,
        gt=0,
        description="Number of shares traded (size / price)",
    )

    fee: float | None = Field(
        default=None,
        ge=0,
        description="Trading fee paid in USDC",
    )

    @field_validator("maker", "taker", mode="before")
    @classmethod
    def lowercase_address(cls, v: str | None) -> str | None:
        """Normalize Ethereum addresses to lowercase."""
        return v.lower() if v else None

    @model_validator(mode="after")
    def compute_shares(self) -> "Trade":
        """Compute shares if not provided."""
        if self.shares is None and self.price > 0:
            self.shares = self.size / self.price
        return self


class Position(BaseModel):
    """
    Represents a wallet's position in a specific market outcome.

    A position is the net holding of shares in a particular outcome.
    Positive = long, Negative = short (if supported).
    """

    wallet: str = Field(
        ...,
        description="Wallet address holding the position",
    )

    market_id: str = Field(
        ...,
        description="Condition ID of the market",
    )

    outcome: str = Field(
        ...,
        description="The outcome this position is in",
    )

    size: float = Field(
        ...,
        description="Current position size in USDC (positive = long, negative = short)",
    )

    avg_price: float = Field(
        ...,
        ge=0,
        le=1,
        description="Average entry price per share",
    )

    shares: float = Field(
        ...,
        description="Number of shares held (size / avg_price)",
    )

    unrealized_pnl: float = Field(
        default=0.0,
        description="Unrealized PnL if position were closed at current price",
    )

    @field_validator("wallet", mode="before")
    @classmethod
    def lowercase_address(cls, v: str) -> str:
        """Normalize Ethereum address to lowercase."""
        return v.lower()


class ExecutedTrade(BaseModel):
    """
    Represents a trade executed by the follower during backtesting.

    This is different from Trade - it's the action our backtest system
    took in response to a target wallet's activity.
    """

    timestamp: datetime = Field(
        ...,
        description="When the trade was executed (may differ from target trade time)",
    )

    market_id: str = Field(
        ...,
        description="Condition ID of the market",
    )

    side: Literal["buy", "sell"] = Field(
        ...,
        description="Buy (long) or sell (short)",
    )

    price: float = Field(
        ...,
        ge=0,
        le=1,
        description="Execution price per share",
    )

    size: float = Field(
        ...,
        description="Trade size in USDC",
    )

    shares: float = Field(
        ...,
        gt=0,
        description="Number of shares traded",
    )

    slippage_bps: float = Field(
        default=0.0,
        ge=0,
        description="Slippage in basis points applied to this trade",
    )

    fee: float = Field(
        default=0.0,
        ge=0,
        description="Trading fee in USDC",
    )

    target_trade_hash: str | None = Field(
        default=None,
        description="Transaction hash of the target trade that triggered this",
    )

    reason: str = Field(
        default="",
        description="Why this trade was executed (e.g., 'mirror_latency', 'rebalance')",
    )


class BacktestState(BaseModel):
    """
    Represents the state of a backtest at a point in time.

    The state evolves as trades are executed during the backtest.
    """

    cash: float = Field(
        ...,
        ge=0,
        description="Available cash in USDC",
    )

    positions: dict[str, Position] = Field(
        default_factory=dict,
        description="Current positions by key (market_id:outcome)",
    )

    trade_log: list[ExecutedTrade] = Field(
        default_factory=list,
        description="History of executed trades",
    )

    timestamps: list[datetime] = Field(
        default_factory=list,
        description="Timestamps when state was modified",
    )

    starting_cash: float = Field(
        ...,
        ge=0,
        description="Initial capital (for calculating returns)",
    )

    @property
    def equity(self) -> float:
        """Total equity = cash + position values."""
        position_value = sum(p.size for p in self.positions.values())
        return self.cash + position_value

    @property
    def total_return(self) -> float:
        """Return as a percentage of starting capital."""
        if self.starting_cash == 0:
            return 0.0
        return (self.equity - self.starting_cash) / self.starting_cash

    @property
    def exposure(self) -> float:
        """Total capital deployed in positions."""
        return sum(abs(p.size) for p in self.positions.values())

    def get_position(self, market_id: str, outcome: str) -> Position | None:
        """Get a position by market and outcome."""
        key = f"{market_id}:{outcome}"
        return self.positions.get(key)

    def update_position(
        self,
        market_id: str,
        outcome: str,
        size_delta: float,
        price: float,
    ) -> None:
        """
        Update a position after a trade.

        Args:
            market_id: Market condition ID
            outcome: Outcome being traded
            size_delta: Change in position size (positive = buy, negative = sell)
            price: Execution price
        """
        key = f"{market_id}:{outcome}"

        if key in self.positions:
            # Update existing position
            pos = self.positions[key]
            old_size = pos.size
            old_cost = pos.size  # For binary options, size ≈ cost basis

            new_size = old_size + size_delta

            if abs(new_size) < 0.01:  # Close position if near zero
                del self.positions[key]
            else:
                # Calculate new average price
                new_cost = old_cost + size_delta
                new_avg_price = abs(new_cost / new_size) if new_size != 0 else price

                self.positions[key] = Position(
                    wallet=self.positions[key].wallet,
                    market_id=market_id,
                    outcome=outcome,
                    size=new_size,
                    avg_price=new_avg_price,
                    shares=abs(new_size / new_avg_price) if new_avg_price > 0 else 0,
                )
        else:
            # Open new position
            if abs(size_delta) >= 0.01:
                self.positions[key] = Position(
                    wallet="follower",  # Placeholder
                    market_id=market_id,
                    outcome=outcome,
                    size=size_delta,
                    avg_price=price,
                    shares=abs(size_delta / price) if price > 0 else 0,
                )


class BacktestMetrics(BaseModel):
    """
    Performance metrics calculated from a completed backtest.
    """

    # Return metrics
    total_return: float = Field(
        ...,
        description="Total return as a decimal (e.g., 0.15 = 15%)",
    )

    sharpe_ratio: float = Field(
        ...,
        description="Sharpe ratio (annualized return / volatility)",
    )

    sortino_ratio: float = Field(
        ...,
        description="Sortino ratio (downside-risk-adjusted return)",
    )

    max_drawdown: float = Field(
        ...,
        ge=0,
        le=1,
        description="Maximum drawdown as a decimal (e.g., 0.20 = 20%)",
    )

    max_drawdown_duration: timedelta = Field(
        ...,
        description="Longest time spent in drawdown",
    )

    # Trade metrics
    total_trades: int = Field(
        ...,
        ge=0,
        description="Total number of trades executed",
    )

    win_rate: float = Field(
        ...,
        ge=0,
        le=1,
        description="Percentage of trades that were profitable",
    )

    avg_trade_return: float = Field(
        ...,
        description="Average return per trade as a decimal",
    )

    skipped_trades: int = Field(
        ...,
        ge=0,
        description="Number of target trades not followed",
    )

    skipped_rate: float = Field(
        ...,
        ge=0,
        le=1,
        description="Percentage of trades skipped",
    )

    # Exposure metrics
    max_exposure: float = Field(
        ...,
        ge=0,
        description="Maximum capital deployed in positions at any time",
    )

    avg_exposure: float = Field(
        ...,
        ge=0,
        description="Average capital deployed in positions",
    )

    exposure_by_market: dict[str, float] = Field(
        default_factory=dict,
        description="Total exposure per market",
    )

    # Comparison vs target
    target_return: float = Field(
        ...,
        description="Target wallet's return over the same period",
    )

    correlation: float | None = Field(
        default=None,
        ge=-1,
        le=1,
        description="Correlation between follower and target returns",
    )

    # Additional computed metrics
    final_equity: float = Field(
        ...,
        description="Final equity value in USDC",
    )

    peak_equity: float = Field(
        ...,
        description="Highest equity value reached",
    )

    total_fees: float = Field(
        default=0.0,
        ge=0,
        description="Total fees paid in USDC",
    )

    @property
    def total_return_pct(self) -> str:
        """Total return as a formatted percentage string."""
        return f"{self.total_return * 100:.2f}%"

    @property
    def win_rate_pct(self) -> str:
        """Win rate as a formatted percentage string."""
        return f"{self.win_rate * 100:.1f}%"
