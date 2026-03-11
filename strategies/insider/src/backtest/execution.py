"""
Order execution logic for backtesting.

Handles:
- Slippage
- Commission
- OHLC-based stop/take fills
- Conservative fill assumptions
"""
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, Tuple, Literal

from ..normalize.schema import PriceBar, Fill

logger = logging.getLogger(__name__)


class ExecutionModel:
    """
    Simulate order execution with realistic costs and slippage.
    """

    def __init__(
        self,
        commission_per_share: Decimal = Decimal("0.005"),
        min_commission: Decimal = Decimal("1.0"),
        slippage_bps: Decimal = Decimal("2"),  # 2 basis points
        fill_assumption: Literal["worst", "best", "open_first"] = "worst",
    ):
        """
        Initialize execution model.

        Args:
            commission_per_share: Commission per share traded
            min_commission: Minimum commission per order
            slippage_bps: Slippage in basis points (0.01% per bps)
            fill_assumption: When both stop and take hit in same bar:
                - "worst": Assume stop fills first (conservative)
                - "best": Assume take fills first (optimistic)
                - "open_first": Check stops/takes from open price
        """
        self.commission_per_share = commission_per_share
        self.min_commission = min_commission
        self.slippage_bps = slippage_bps
        self.fill_assumption = fill_assumption

    def calculate_commission(self, shares: Decimal) -> Decimal:
        """Calculate commission for a trade."""
        comm = shares * self.commission_per_share
        return max(comm, self.min_commission)

    def fill_at_open(self, bar: PriceBar, side: str, shares: Decimal, timestamp: datetime) -> Fill:
        """
        Fill an order at the bar's open with slippage.

        Args:
            bar: Price bar to fill against
            side: "buy" or "sell"
            shares: Number of shares
            timestamp: Fill timestamp

        Returns:
            Fill object
        """
        price = bar.open
        commission = self.calculate_commission(shares)

        # Apply slippage (worsens price)
        slippage_factor = Decimal("1")
        if side == "buy":
            slippage_factor = Decimal("1") + (self.slippage_bps / Decimal("10000"))
        else:
            slippage_factor = Decimal("1") - (self.slippage_bps / Decimal("10000"))

        fill_price = price * slippage_factor

        return Fill(
            datetime=timestamp,
            ticker="",  # Will be set by caller
            side=side,
            shares=shares,
            price=fill_price,
            commission=commission,
            slippage_bps=self.slippage_bps,
        )

    def fill_at_close(self, bar: PriceBar, side: str, shares: Decimal, timestamp: datetime) -> Fill:
        """Fill an order at the bar's close with slippage."""
        price = bar.close
        commission = self.calculate_commission(shares)

        # Apply slippage
        slippage_factor = Decimal("1")
        if side == "buy":
            slippage_factor = Decimal("1") + (self.slippage_bps / Decimal("10000"))
        else:
            slippage_factor = Decimal("1") - (self.slippage_bps / Decimal("10000"))

        fill_price = price * slippage_factor

        return Fill(
            datetime=timestamp,
            ticker="",
            side=side,
            shares=shares,
            price=fill_price,
            commission=commission,
            slippage_bps=self.slippage_bps,
        )

    def fill_at_stop(
        self,
        bar: PriceBar,
        stop_price: Decimal,
        shares: Decimal,
        timestamp: datetime
    ) -> Optional[Fill]:
        """
        Check if stop loss is hit and create fill.

        Stop is hit if: bar.low <= stop_price

        Fill price: stop_price (with slight adverse slippage)
        """
        if bar.low <= stop_price:
            commission = self.calculate_commission(shares)

            # Stop fills at stop price with slippage
            slippage_factor = Decimal("1") - (self.slippage_bps / Decimal("10000"))
            fill_price = stop_price * slippage_factor

            return Fill(
                datetime=timestamp,
                ticker="",
                side="sell",
                shares=shares,
                price=fill_price,
                commission=commission,
                slippage_bps=self.slippage_bps,
            )

        return None

    def fill_at_take(
        self,
        bar: PriceBar,
        take_price: Decimal,
        shares: Decimal,
        timestamp: datetime
    ) -> Optional[Fill]:
        """
        Check if take profit is hit and create fill.

        Take is hit if: bar.high >= take_price

        Fill price: take_price (with slippage)
        """
        if bar.high >= take_price:
            commission = self.calculate_commission(shares)

            # Take fills at take price with slippage
            slippage_factor = Decimal("1") - (self.slippage_bps / Decimal("10000"))
            fill_price = take_price * slippage_factor

            return Fill(
                datetime=timestamp,
                ticker="",
                side="sell",
                shares=shares,
                price=fill_price,
                commission=commission,
                slippage_bps=self.slippage_bps,
            )

        return None

    def check_bracket_exit(
        self,
        bar: PriceBar,
        entry_price: Decimal,
        shares: Decimal,
        stop_loss_pct: Decimal,
        take_profit_pct: Decimal,
        timestamp: datetime,
        trailing_stop_r: Optional[int] = None,
        highest_price: Optional[Decimal] = None,
    ) -> Tuple[Optional[Fill], str, Optional[Decimal]]:
        """
        Check for bracket exit (stop loss or take profit).

        Args:
            bar: Current price bar
            entry_price: Entry price
            shares: Position size
            stop_loss_pct: Stop loss percentage (e.g., 0.08 for 8%)
            take_profit_pct: Take profit percentage (e.g., 0.16 for 16%)
            timestamp: Current timestamp
            trailing_stop_r: If set, use trailing stops at R multiples (e.g., 2 for 1R/2R)
            highest_price: Highest price since entry (for trailing stops)

        Returns:
            Tuple of (fill or None, exit_reason, new_highest_price)
            exit_reason: "stop_loss", "take_profit", "trailing_stop", "both_stop", "both_take", or None
        """
        # Calculate initial risk amount (R)
        initial_r = entry_price * stop_loss_pct

        # Determine stop price
        if trailing_stop_r and highest_price is not None:
            # Update highest price
            if bar.high > highest_price:
                highest_price = bar.high

            # Calculate R multiples gained
            profit = highest_price - entry_price
            r_multiple = profit / initial_r if initial_r > 0 else Decimal("0")

            # Trailing stop logic
            if r_multiple >= 2:
                # Move stop to +1R (lock in 1R profit)
                stop_price = entry_price + initial_r
            elif r_multiple >= 1:
                # Move stop to breakeven
                stop_price = entry_price
            else:
                # Still using initial stop
                stop_price = entry_price * (Decimal("1") - stop_loss_pct)
        else:
            # Static stop
            stop_price = entry_price * (Decimal("1") - stop_loss_pct)
            highest_price = bar.high if bar.high > (highest_price or entry_price) else (highest_price or entry_price)

        take_price = entry_price * (Decimal("1") + take_profit_pct)

        stop_hit = bar.low <= stop_price
        take_hit = bar.high >= take_price

        if not stop_hit and not take_hit:
            return None, "", highest_price

        if stop_hit and not take_hit:
            fill = self.fill_at_stop(bar, stop_price, shares, timestamp)
            reason = "trailing_stop" if trailing_stop_r else "stop_loss"
            return fill, reason, highest_price

        if take_hit and not stop_hit:
            fill = self.fill_at_take(bar, take_price, shares, timestamp)
            return fill, "take_profit", highest_price

        # Both hit in same bar - use fill_assumption
        if self.fill_assumption == "worst":
            fill = self.fill_at_stop(bar, stop_price, shares, timestamp)
            return fill, "both_stop", highest_price
        elif self.fill_assumption == "best":
            fill = self.fill_at_take(bar, take_price, shares, timestamp)
            return fill, "both_take", highest_price
        else:  # open_first
            # Check which level is closer to open
            if bar.open <= stop_price:
                fill = self.fill_at_stop(bar, stop_price, shares, timestamp)
                return fill, "both_stop", highest_price
            else:
                fill = self.fill_at_take(bar, take_price, shares, timestamp)
                return fill, "both_take", highest_price
