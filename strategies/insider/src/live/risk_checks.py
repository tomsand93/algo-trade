"""
Risk management checks for paper trading.

Provides:
- Position size validation
- Account balance checks
- Daily loss limits
- Exposure limits
"""
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Tuple

from .alpaca_paper import AlpacaPaperClient

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Risk management for paper trading.

    Validates orders before submission.
    """

    def __init__(
        self,
        client: AlpacaPaperClient,
        max_position_size_pct: Decimal = Decimal("0.15"),
        max_total_exposure_pct: Decimal = Decimal("0.95"),
        daily_loss_limit_pct: Optional[Decimal] = None,
        max_drawdown_pct: Optional[Decimal] = None,
    ):
        """
        Initialize risk manager.

        Args:
            client: Alpaca paper trading client
            max_position_size_pct: Max single position as % of equity
            max_total_exposure_pct: Max total exposure as % of equity
            daily_loss_limit_pct: Daily loss limit (e.g., 0.05 for 5%)
            max_drawdown_pct: Max drawdown from peak (e.g., 0.15 for 15%)
        """
        self.client = client
        self.max_position_size_pct = max_position_size_pct
        self.max_total_exposure_pct = max_total_exposure_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.max_drawdown_pct = max_drawdown_pct

        # Track daily starting equity
        self.daily_start_equity: Optional[Decimal] = None
        self.peak_equity: Optional[Decimal] = None

        # Initialize
        self._reset_daily_tracking()

    def _reset_daily_tracking(self) -> None:
        """Reset daily tracking variables."""
        config = self.client.get_account_config()
        current_equity = config["portfolio_value"]

        if self.daily_start_equity is None:
            self.daily_start_equity = current_equity

        if self.peak_equity is None or current_equity > self.peak_equity:
            self.peak_equity = current_equity

    def can_open_position(
        self,
        symbol: str,
        shares: Decimal,
        price: Decimal,
    ) -> Tuple[bool, str]:
        """
        Check if a new position can be opened.

        Args:
            symbol: Ticker symbol
            shares: Number of shares
            price: Entry price per share

        Returns:
            Tuple of (allowed, reason)
        """
        config = self.client.get_account_config()
        equity = config["portfolio_value"]
        buying_power = config["buying_power"]

        position_value = shares * price

        # Check 1: Sufficient buying power
        if position_value > buying_power * Decimal("0.95"):
            return False, f"Insufficient buying power: need ${position_value:.2f}, have ${buying_power:.2f}"

        # Check 2: Position size limit
        position_pct = position_value / equity
        if position_pct > self.max_position_size_pct:
            return False, f"Position too large: {position_pct*100:.1f}% > {self.max_position_size_pct*100:.1f}%"

        # Check 3: Total exposure
        current_positions = self.client.get_positions()
        current_exposure = sum(p.market_value for p in current_positions)
        new_exposure = current_exposure + position_value
        exposure_pct = new_exposure / equity

        if exposure_pct > self.max_total_exposure_pct:
            return False, f"Total exposure too high: {exposure_pct*100:.1f}% > {self.max_total_exposure_pct*100:.1f}%"

        # Check 4: Daily loss limit
        if self.daily_loss_limit_pct:
            daily_pnl_pct = (equity - self.daily_start_equity) / self.daily_start_equity
            if daily_pnl_pct < -self.daily_loss_limit_pct:
                return False, f"Daily loss limit reached: {daily_pnl_pct*100:.2f}% < {-self.daily_loss_limit_pct*100:.1f}%"

        # Check 5: Max drawdown
        if self.max_drawdown_pct and self.peak_equity:
            drawdown_pct = (self.peak_equity - equity) / self.peak_equity
            if drawdown_pct > self.max_drawdown_pct:
                return False, f"Max drawdown exceeded: {drawdown_pct*100:.2f}% > {self.max_drawdown_pct*100:.1f}%"

        return True, ""

    def validate_order_size(
        self,
        symbol: str,
        requested_shares: Decimal,
        price: Decimal,
    ) -> Decimal:
        """
        Validate and adjust order size if needed.

        Args:
            symbol: Ticker symbol
            requested_shares: Requested number of shares
            price: Price per share

        Returns:
            Approved number of shares (may be 0)
        """
        can_open, reason = self.can_open_position(symbol, requested_shares, price)

        if not can_open:
            logger.warning(f"Order rejected for {symbol}: {reason}")
            return Decimal("0")

        return requested_shares

    def check_halt_trading(self) -> Tuple[bool, str]:
        """
        Check if trading should be halted due to risk limits.

        Returns:
            Tuple of (halt, reason)
        """
        config = self.client.get_account_config()
        equity = config["portfolio_value"]

        # Check daily loss limit
        if self.daily_loss_limit_pct:
            daily_pnl_pct = (equity - self.daily_start_equity) / self.daily_start_equity
            if daily_pnl_pct < -self.daily_loss_limit_pct:
                return True, f"Daily loss limit reached: {daily_pnl_pct*100:.2f}%"

        # Check max drawdown
        if self.max_drawdown_pct and self.peak_equity:
            drawdown_pct = (self.peak_equity - equity) / self.peak_equity
            if drawdown_pct > self.max_drawdown_pct:
                return True, f"Max drawdown exceeded: {drawdown_pct*100:.2f}%"

        return False, ""

    def reset_daily(self) -> None:
        """Reset daily tracking (call at start of trading day)."""
        self.daily_start_equity = None
        self._reset_daily_tracking()
        logger.info("Daily risk tracking reset")

    def get_status(self) -> dict:
        """Get current risk manager status."""
        config = self.client.get_account_config()
        equity = config["portfolio_value"]

        status = {
            "max_position_size_pct": str(self.max_position_size_pct),
            "max_total_exposure_pct": str(self.max_total_exposure_pct),
            "daily_loss_limit_pct": str(self.daily_loss_limit_pct) if self.daily_loss_limit_pct else None,
            "max_drawdown_pct": str(self.max_drawdown_pct) if self.max_drawdown_pct else None,
            "current_equity": str(equity),
            "daily_start_equity": str(self.daily_start_equity) if self.daily_start_equity else None,
            "peak_equity": str(self.peak_equity) if self.peak_equity else None,
        }

        if self.daily_start_equity:
            daily_pnl_pct = (equity - self.daily_start_equity) / self.daily_start_equity
            status["daily_pnl_pct"] = f"{daily_pnl_pct*100:.2f}%"

        if self.peak_equity:
            drawdown_pct = (self.peak_equity - equity) / self.peak_equity
            status["current_drawdown_pct"] = f"{drawdown_pct*100:.2f}%"

        return status
