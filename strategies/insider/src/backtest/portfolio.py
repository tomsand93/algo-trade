"""
Portfolio management for backtesting.

Handles:
- Position tracking
- Cash and equity calculation
- Position sizing
- Risk limits (max positions, sector exposure)
"""
import logging
from datetime import date
from decimal import Decimal
from typing import List, Optional, Dict, Tuple

from ..normalize.schema import Position, TradeResult, PortfolioSnapshot

logger = logging.getLogger(__name__)


class Portfolio:
    """
    Manage portfolio state during backtest.
    """

    def __init__(
        self,
        initial_cash: Decimal = Decimal("100000"),
        position_size_pct: Decimal = Decimal("0.10"),  # 10% per trade
        max_positions: int = 5,
        max_daily_new_positions: int = 3,
    ):
        """
        Initialize portfolio.

        Args:
            initial_cash: Starting cash
            position_size_pct: Percentage of equity to allocate per trade
            max_positions: Maximum concurrent positions
            max_daily_new_positions: Maximum new positions per day
        """
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.position_size_pct = position_size_pct
        self.max_positions = max_positions
        self.max_daily_new_positions = max_daily_new_positions

        self.positions: Dict[str, Position] = {}  # ticker -> Position
        self.closed_trades: List[TradeResult] = []
        self.snapshots: List[PortfolioSnapshot] = []

        self.today_new_positions = 0
        self.equity_peak: Decimal = initial_cash

    @property
    def equity(self) -> Decimal:
        """Current total equity (cash + positions)."""
        return self.cash  # Positions valued separately

    @property
    def n_positions(self) -> int:
        """Number of open positions."""
        return len(self.positions)

    def can_open_position(self, ticker: str, current_date: date) -> Tuple[bool, str]:
        """
        Check if a new position can be opened.

        Args:
            ticker: Ticker to trade
            current_date: Current date

        Returns:
            Tuple of (can_open, reason)
        """
        if ticker in self.positions:
            return False, "already_holding"

        if self.n_positions >= self.max_positions:
            return False, "max_positions"

        if self.today_new_positions >= self.max_daily_new_positions:
            return False, "max_daily_positions"

        return True, ""

    def calculate_position_size(
        self,
        price: Decimal,
        current_date: date
    ) -> Optional[Decimal]:
        """
        Calculate position size in shares.

        Args:
            price: Entry price per share
            current_date: Current date

        Returns:
            Number of shares or None if insufficient cash
        """
        # Allocate percentage of current equity
        target_value = self.equity * self.position_size_pct

        # Check we have enough cash
        if target_value > self.cash * Decimal("0.95"):  # Leave 5% buffer
            return None

        # Calculate shares (round down to whole shares)
        shares = int(target_value / price)

        if shares <= 0:
            return None

        return Decimal(str(shares))

    def open_position(
        self,
        ticker: str,
        entry_date: date,
        entry_price: Decimal,
        shares: Decimal,
        entry_bar_index: int,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
    ) -> bool:
        """
        Open a new position.

        Args:
            ticker: Ticker symbol
            entry_date: Entry date
            entry_price: Entry price
            shares: Number of shares
            entry_bar_index: Bar index for tracking
            stop_loss: Optional stop loss price
            take_profit: Optional take profit price

        Returns:
            True if position opened successfully
        """
        # Calculate cost
        cost = entry_price * shares

        if cost > self.cash:
            logger.warning(f"Insufficient cash to open {ticker} position")
            return False

        # Deduct cash
        self.cash -= cost

        # Create position
        self.positions[ticker] = Position(
            ticker=ticker,
            entry_date=entry_date,
            entry_price=entry_price,
            shares=shares,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_bar_index=entry_bar_index,
        )

        self.today_new_positions += 1

        logger.info(
            f"Opened {ticker}: {shares} shares @ ${entry_price:.2f}, "
            f"cost: ${cost:.2f}, cash: ${self.cash:.2f}"
        )

        return True

    def close_position(
        self,
        ticker: str,
        exit_date: date,
        exit_price: Decimal,
        exit_reason: str,
        costs: Decimal,
        current_bar_index: int,
    ) -> Optional[TradeResult]:
        """
        Close an existing position.

        Args:
            ticker: Ticker symbol
            exit_date: Exit date
            exit_price: Exit price
            exit_reason: Reason for exit
            costs: Trading costs
            current_bar_index: Current bar index

        Returns:
            TradeResult if position existed and was closed
        """
        position = self.positions.pop(ticker, None)
        if position is None:
            logger.warning(f"No position found for {ticker}")
            return None

        # Add proceeds to cash (minus costs)
        proceeds = exit_price * position.shares
        self.cash += proceeds - costs

        # Calculate PnL
        gross_pnl = (exit_price - position.entry_price) * position.shares
        net_pnl = gross_pnl - costs
        pnl_pct = (exit_price - position.entry_price) / position.entry_price

        hold_bars = current_bar_index - position.entry_bar_index

        result = TradeResult(
            ticker=ticker,
            entry_date=position.entry_date,
            exit_date=exit_date,
            entry_price=position.entry_price,
            exit_price=exit_price,
            shares=position.shares,
            gross_pnl=gross_pnl,
            costs=costs,
            net_pnl=net_pnl,
            pnl_pct=pnl_pct,
            hold_bars=hold_bars,
            exit_reason=exit_reason,
        )

        self.closed_trades.append(result)

        logger.info(
            f"Closed {ticker} ({exit_reason}): "
            f"{position.shares} shares @ ${exit_price:.2f}, "
            f"PnL: ${net_pnl:.2f} ({pnl_pct*100:.2f}%), "
            f"hold: {hold_bars} bars, cash: ${self.cash:.2f}"
        )

        return result

    def update_positions_value(self, prices: Dict[str, Decimal]) -> Decimal:
        """
        Update and return total value of open positions.

        Args:
            prices: Current price for each held ticker

        Returns:
            Total market value of positions
        """
        total_value = Decimal("0")
        for ticker, position in self.positions.items():
            price = prices.get(ticker, position.entry_price)
            total_value += position.shares * price

        return total_value

    def get_total_equity(self, prices: Dict[str, Decimal]) -> Decimal:
        """Get total equity (cash + positions)."""
        return self.cash + self.update_positions_value(prices)

    def create_snapshot(
        self,
        snapshot_date: date,
        prices: Dict[str, Decimal],
    ) -> PortfolioSnapshot:
        """Create a portfolio snapshot."""
        positions_value = self.update_positions_value(prices)
        total_equity = self.cash + positions_value

        # Update peak equity for drawdown
        if total_equity > self.equity_peak:
            self.equity_peak = total_equity

        drawdown = (self.equity_peak - total_equity) / self.equity_peak

        snapshot = PortfolioSnapshot(
            date=snapshot_date,
            equity=total_equity,
            cash=self.cash,
            positions_value=positions_value,
            n_positions=self.n_positions,
            drawdown=drawdown,
        )

        self.snapshots.append(snapshot)
        return snapshot

    def reset_daily_counters(self):
        """Reset daily position counter."""
        self.today_new_positions = 0

    def force_close_all(
        self,
        exit_date: date,
        prices: Dict[str, Decimal],
        costs_per_share: Decimal,
        current_bar_index: int,
    ) -> List[TradeResult]:
        """
        Force close all positions at current prices.

        Args:
            exit_date: Exit date
            prices: Current prices
            costs_per_share: Cost per share to close
            current_bar_index: Current bar index

        Returns:
            List of TradeResults
        """
        results = []
        tickers = list(self.positions.keys())

        for ticker in tickers:
            position = self.positions[ticker]
            price = prices.get(ticker, position.entry_price)
            costs = costs_per_share * position.shares

            result = self.close_position(
                ticker=ticker,
                exit_date=exit_date,
                exit_price=price,
                exit_reason="force_close",
                costs=costs,
                current_bar_index=current_bar_index,
            )
            if result:
                results.append(result)

        return results

    def get_historical_equity(self) -> List[Tuple[date, Decimal]]:
        """Get equity curve from snapshots."""
        return [(s.date, s.equity) for s in self.snapshots]
