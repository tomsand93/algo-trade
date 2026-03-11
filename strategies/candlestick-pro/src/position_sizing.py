"""
Dynamic Position Sizing for Candlestick Pro

Implements advanced position sizing strategies:
1. Kelly Criterion - Optimal sizing based on edge and odds
2. Drawdown-Based Sizing - Reduce risk after losses
3. Risk of Ruin calculations

The Kelly Criterion formula:
    f* = (p*b - q) / b

Where:
    f* = fraction of capital to wager
    p = probability of winning
    q = probability of losing (1 - p)
    b = odds received on the wager (win/loss ratio)
"""

from typing import Optional, List, Tuple
from dataclasses import dataclass
import math


@dataclass
class PositionSizeResult:
    """Result of position sizing calculation"""
    size: float           # Position size in units
    risk_amount: float    # Amount risked in currency
    risk_pct: float       # Percentage of capital risked
    method: str           # Method used (e.g., "Kelly", "Fixed 1%", "Drawdown Reduced")
    kelly_fraction: Optional[float] = None  # Kelly fraction if applicable


class DynamicPositionSizer:
    """
    Advanced position sizing with multiple strategies.

    Strategies:
    1. Kelly Criterion - Mathematically optimal sizing
    2. Half-Kelly - More conservative version of Kelly
    3. Fixed Percentage - Simple fixed risk per trade
    4. Drawdown-Adjusted - Reduces size after drawdowns
    """

    def __init__(
        self,
        initial_capital: float,
        default_risk_pct: float = 0.01,  # 1% default risk
        max_position_pct: float = 0.20,   # 20% max position size
        kelly_fraction: float = 0.5,      # Use half-Kelly by default (safer)
    ):
        """
        Initialize the position sizer.

        Args:
            initial_capital: Starting capital
            default_risk_pct: Default risk per trade (e.g., 0.01 = 1%)
            max_position_pct: Maximum position as % of capital
            kelly_fraction: Kelly multiplier (0.5 = half-Kelly, 1.0 = full Kelly)
        """
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.peak_capital = initial_capital
        self.default_risk_pct = default_risk_pct
        self.max_position_pct = max_position_pct
        self.kelly_fraction = kelly_fraction

        # Track trade history for adaptive sizing
        self.trade_history: List[dict] = []  # List of {'pnl': float, 'risk': float}
        self.win_rate_history: List[float] = []
        self.win_loss_ratio_history: List[float] = []

    def calculate_kelly_fraction(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
    ) -> float:
        """
        Calculate the Kelly Criterion fraction.

        Kelly formula: f* = (p*b - q) / b
        where p = win_rate, q = 1-p, b = avg_win/avg_loss

        Returns 0 if Kelly is negative (no edge).
        """
        if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
            return 0.0

        win_loss_ratio = avg_win / abs(avg_loss)
        q = 1 - win_rate

        # Kelly formula
        kelly = (win_rate * win_loss_ratio - q) / win_loss_ratio

        # Don't bet if no edge
        if kelly <= 0:
            return 0.0

        # Cap Kelly at reasonable levels (full Kelly is aggressive)
        kelly = min(kelly, 0.25)  # Max 25% of capital per trade

        return kelly

    def calculate_drawdown_multiplier(self) -> float:
        """
        Calculate position size reduction based on drawdown.

        Reduces position size as drawdown increases:
        - 0% DD: 100% size
        - 5% DD: 100% size
        - 10% DD: 75% size
        - 15% DD: 50% size
        - 20% DD: 25% size
        - 25% DD: 0% size (stop trading)
        """
        drawdown_pct = (self.peak_capital - self.current_capital) / self.peak_capital

        if drawdown_pct <= 0.05:
            return 1.0  # No reduction for small DD
        elif drawdown_pct <= 0.10:
            return 0.75  # 25% reduction
        elif drawdown_pct <= 0.15:
            return 0.50  # 50% reduction
        elif drawdown_pct <= 0.20:
            return 0.25  # 75% reduction
        else:
            return 0.0  # Stop trading after 20% DD

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        method: str = "kelly",
        win_rate: Optional[float] = None,
        avg_win: Optional[float] = None,
        avg_loss: Optional[float] = None,
        fee_pct: float = 0.001,
    ) -> PositionSizeResult:
        """
        Calculate optimal position size.

        Args:
            entry_price: Entry price per unit
            stop_loss: Stop loss price
            method: "kelly", "fixed", "adaptive", or "drawdown"
            win_rate: Historical win rate (for Kelly)
            avg_win: Average win amount (for Kelly)
            avg_loss: Average loss amount (for Kelly)
            fee_pct: Trading fee percentage

        Returns:
            PositionSizeResult with size and details
        """
        risk_per_unit = abs(entry_price - stop_loss)

        if risk_per_unit <= 1e-10:
            return PositionSizeResult(
                size=0.0, risk_amount=0.0, risk_pct=0.0, method="No Risk"
            )

        # Calculate base risk amount based on method
        if method == "kelly" and win_rate is not None and avg_win is not None and avg_loss is not None:
            # Kelly Criterion sizing
            kelly_f = self.calculate_kelly_fraction(win_rate, avg_win, avg_loss)
            adjusted_kelly = kelly_f * self.kelly_fraction  # Apply half-Kelly or other
            risk_amount = self.current_capital * adjusted_kelly
            method_str = f"Kelly ({adjusted_kelly:.1%})"
            kelly_frac = adjusted_kelly
        elif method == "drawdown":
            # Drawdown-adjusted fixed sizing
            multiplier = self.calculate_drawdown_multiplier()
            risk_amount = self.current_capital * self.default_risk_pct * multiplier
            method_str = f"Drawdown Adj ({multiplier:.0%} of base)"
            kelly_frac = None
        else:
            # Fixed percentage sizing
            risk_amount = self.current_capital * self.default_risk_pct
            method_str = f"Fixed {self.default_risk_pct:.1%}"
            kelly_frac = None

        # Calculate size from risk amount
        size_from_risk = risk_amount / risk_per_unit

        # Cap by maximum position size
        max_notional = self.current_capital * self.max_position_pct
        max_size = max_notional / entry_price
        final_size = min(size_from_risk, max_size)

        # Verify we can afford entry + fees
        required_capital = final_size * entry_price * (1 + fee_pct)
        if required_capital > self.current_capital:
            final_size = (self.current_capital * 0.95) / (entry_price * (1 + fee_pct))

        actual_risk_amount = final_size * risk_per_unit
        actual_risk_pct = actual_risk_amount / self.current_capital

        return PositionSizeResult(
            size=max(0.0, final_size),
            risk_amount=actual_risk_amount,
            risk_pct=actual_risk_pct,
            method=method_str,
            kelly_fraction=kelly_frac,
        )

    def update_capital(self, new_capital: float):
        """Update current capital and track peak."""
        self.current_capital = new_capital
        self.peak_capital = max(self.peak_capital, new_capital)

    def add_trade_result(self, pnl: float, risked: float):
        """Record a trade result for adaptive sizing."""
        self.trade_history.append({'pnl': pnl, 'risk': risked})

        # Recalculate statistics
        if len(self.trade_history) >= 10:  # Need at least 10 trades
            wins = [t for t in self.trade_history if t['pnl'] > 0]
            losses = [t for t in self.trade_history if t['pnl'] < 0]

            if wins and losses:
                win_rate = len(wins) / len(self.trade_history)
                avg_win = sum(t['pnl'] for t in wins) / len(wins)
                avg_loss = sum(t['pnl'] for t in losses) / len(losses)

                self.win_rate_history.append(win_rate)
                self.win_loss_ratio_history.append(abs(avg_win / avg_loss))

    def get_adaptive_stats(self) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Get adaptive statistics for position sizing.

        Returns:
            (win_rate, avg_win, avg_loss) or (None, None, None) if insufficient data
        """
        if len(self.trade_history) < 10:
            return None, None, None

        wins = [t for t in self.trade_history if t['pnl'] > 0]
        losses = [t for t in self.trade_history if t['pnl'] < 0]

        if not wins or not losses:
            return None, None, None

        win_rate = len(wins) / len(self.trade_history)
        avg_win = sum(t['pnl'] for t in wins) / len(wins)
        avg_loss = sum(t['pnl'] for t in losses) / len(losses)

        return win_rate, avg_win, avg_loss


def calculate_size_with_historical_stats(
    sizer: DynamicPositionSizer,
    entry_price: float,
    stop_loss: float,
    fee_pct: float = 0.001,
) -> PositionSizeResult:
    """
    Calculate position size using historical statistics if available.

    Uses Kelly Criterion with historical stats, falls back to fixed sizing
    if insufficient data.
    """
    win_rate, avg_win, avg_loss = sizer.get_adaptive_stats()

    if win_rate is not None and avg_win is not None and avg_loss is not None:
        # Use Kelly with historical stats
        return sizer.calculate_position_size(
            entry_price=entry_price,
            stop_loss=stop_loss,
            method="kelly",
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            fee_pct=fee_pct,
        )
    else:
        # Fall back to fixed sizing with drawdown adjustment
        return sizer.calculate_position_size(
            entry_price=entry_price,
            stop_loss=stop_loss,
            method="drawdown",
            fee_pct=fee_pct,
        )
