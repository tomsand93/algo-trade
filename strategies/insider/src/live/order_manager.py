"""
Order manager for paper trading.

Handles:
- Signal-based order submission
- Position monitoring
- Exit order management
"""
import logging
from datetime import date
from decimal import Decimal
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field

from .alpaca_paper import AlpacaPaperClient
from ..normalize.schema import InsiderSignal

logger = logging.getLogger(__name__)


@dataclass
class PositionState:
    """Track state of a managed position."""
    symbol: str
    entry_date: date
    entry_price: Decimal
    shares: Decimal
    stop_loss_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None
    max_hold_bars: int = 60
    hold_bars: int = 0
    alpaca_order_ids: List[str] = field(default_factory=list)
    exit_reason: Optional[str] = None


class OrderManager:
    """
    Manage orders for paper trading.

    Converts signals to orders and monitors positions.
    """

    def __init__(
        self,
        client: AlpacaPaperClient,
        position_size_pct: Decimal = Decimal("0.10"),
        max_positions: int = 5,
        stop_loss_pct: Decimal = Decimal("0.08"),
        take_profit_pct: Decimal = Decimal("0.16"),
        max_hold_bars: int = 60,
        dry_run: bool = False,
    ):
        """
        Initialize order manager.

        Args:
            client: Alpaca paper trading client
            position_size_pct: Percentage of buying power per trade
            max_positions: Maximum concurrent positions
            stop_loss_pct: Stop loss percentage
            take_profit_pct: Take profit percentage
            max_hold_bars: Maximum holding period in bars
            dry_run: If True, log orders without submitting
        """
        self.client = client
        self.position_size_pct = position_size_pct
        self.max_positions = max_positions
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_hold_bars = max_hold_bars
        self.dry_run = dry_run

        # Track managed positions
        self.managed_positions: Dict[str, PositionState] = {}

        # Track processed signals to avoid duplicates
        self.processed_signals: Set[str] = set()

        # Load existing state if available
        self._sync_positions()

    def _sync_positions(self) -> None:
        """Sync managed positions with actual Alpaca positions."""
        try:
            alpaca_positions = self.client.get_positions()

            for pos in alpaca_positions:
                if pos.symbol not in self.managed_positions:
                    self.managed_positions[pos.symbol] = PositionState(
                        symbol=pos.symbol,
                        entry_date=date.today(),
                        entry_price=pos.avg_entry_price,
                        shares=pos.qty,
                        stop_loss_price=None,  # Unknown from existing position
                        take_profit_price=None,
                    )
                    logger.info(f"Synced existing position: {pos.symbol}")

        except Exception as e:
            logger.error(f"Failed to sync positions: {e}")

    def process_signals(self, signals: List[InsiderSignal]) -> None:
        """
        Process new signals and submit entry orders.

        Args:
            signals: List of insider signals
        """
        config = self.client.get_account_config()
        buying_power = config["buying_power"]

        for signal in signals:
            # Skip if already processed
            signal_key = f"{signal.ticker}_{signal.signal_date}"
            if signal_key in self.processed_signals:
                continue

            # Check if already holding
            if signal.ticker in self.managed_positions:
                logger.info(f"Already holding {signal.ticker}, skipping signal")
                self.processed_signals.add(signal_key)
                continue

            # Check max positions
            if len(self.managed_positions) >= self.max_positions:
                logger.info(f"Max positions reached, skipping {signal.ticker}")
                self.processed_signals.add(signal_key)
                continue

            # Submit entry order
            self._submit_entry_order(signal, buying_power)
            self.processed_signals.add(signal_key)

    def _submit_entry_order(self, signal: InsiderSignal, buying_power: Decimal) -> None:
        """Submit entry order for a signal."""
        # Get current price
        current_price = self.client.get_current_price(signal.ticker)
        if current_price is None:
            logger.warning(f"Cannot get price for {signal.ticker}, skipping entry")
            return

        # Calculate position size
        target_value = buying_power * self.position_size_pct
        shares = int(target_value / current_price)

        if shares <= 0:
            logger.warning(f"Insufficient buying power for {signal.ticker}")
            return

        shares = Decimal(str(shares))

        # Calculate stop and take prices
        stop_price = current_price * (Decimal("1") - self.stop_loss_pct)
        take_price = current_price * (Decimal("1") + self.take_profit_pct)

        if self.dry_run:
            logger.info(
                f"[DRY RUN] Would submit bracket order: {signal.ticker} "
                f"buy {shares} shares @ ${current_price:.2f}, "
                f"stop: ${stop_price:.2f}, take: ${take_price:.2f}"
            )
            # Still track the position
            self.managed_positions[signal.ticker] = PositionState(
                symbol=signal.ticker,
                entry_date=date.today(),
                entry_price=current_price,
                shares=shares,
                stop_loss_price=stop_price,
                take_profit_price=take_price,
                max_hold_bars=self.max_hold_bars,
            )
            return

        try:
            # Submit bracket order
            response = self.client.submit_bracket_order(
                symbol=signal.ticker,
                side="buy",
                qty=shares,
                stop_loss_pct=self.stop_loss_pct,
                take_profit_pct=self.take_profit_pct,
            )

            # Track the position
            order_id = response.get("id")
            self.managed_positions[signal.ticker] = PositionState(
                symbol=signal.ticker,
                entry_date=date.today(),
                entry_price=current_price,
                shares=shares,
                stop_loss_price=stop_price,
                take_profit_price=take_price,
                max_hold_bars=self.max_hold_bars,
                alpaca_order_ids=[order_id] if order_id else [],
            )

            logger.info(
                f"Entry submitted for {signal.ticker}: {shares} shares @ ${current_price:.2f}"
            )

        except Exception as e:
            logger.error(f"Failed to submit entry for {signal.ticker}: {e}")

    def monitor_positions(self) -> None:
        """Monitor open positions and check exit conditions."""
        # Refresh from Alpaca to see if positions were closed
        try:
            alpaca_positions = {p.symbol: p for p in self.client.get_positions()}

            positions_to_remove = []

            for symbol, state in self.managed_positions.items():
                if symbol not in alpaca_positions:
                    # Position was closed
                    logger.info(f"Position {symbol} was closed (bracket exit)")
                    positions_to_remove.append(symbol)
                    continue

                # Check max hold
                state.hold_bars += 1
                if state.hold_bars >= state.max_hold_bars:
                    logger.info(f"Max hold reached for {symbol}, closing")
                    self._close_position(symbol, "max_hold")
                    positions_to_remove.append(symbol)

            # Remove closed positions
            for symbol in positions_to_remove:
                del self.managed_positions[symbol]

        except Exception as e:
            logger.error(f"Error monitoring positions: {e}")

    def _close_position(self, symbol: str, reason: str) -> bool:
        """Close a position."""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would close {symbol} ({reason})")
            return True

        try:
            self.client.close_position(symbol)
            logger.info(f"Closed {symbol} ({reason})")
            return True
        except Exception as e:
            logger.error(f"Failed to close {symbol}: {e}")
            return False

    def close_all_positions(self, reason: str = "manual") -> int:
        """Close all managed positions."""
        closed = 0
        symbols = list(self.managed_positions.keys())

        for symbol in symbols:
            if self._close_position(symbol, reason):
                closed += 1
                del self.managed_positions[symbol]

        return closed

    def get_status(self) -> Dict[str, Any]:
        """Get current status of the order manager."""
        return {
            "managed_positions": len(self.managed_positions),
            "max_positions": self.max_positions,
            "processed_signals": len(self.processed_signals),
            "dry_run": self.dry_run,
            "positions": [
                {
                    "symbol": p.symbol,
                    "entry_price": str(p.entry_price),
                    "shares": str(p.shares),
                    "hold_bars": p.hold_bars,
                    "stop_loss": str(p.stop_loss_price) if p.stop_loss_price else None,
                    "take_profit": str(p.take_profit_price) if p.take_profit_price else None,
                }
                for p in self.managed_positions.values()
            ],
        }

    def save_state(self, filepath: str) -> None:
        """Save order manager state to file."""
        import json

        state = {
            "processed_signals": list(self.processed_signals),
            "positions": [
                {
                    "symbol": p.symbol,
                    "entry_date": p.entry_date.isoformat(),
                    "entry_price": str(p.entry_price),
                    "shares": str(p.shares),
                    "stop_loss_price": str(p.stop_loss_price) if p.stop_loss_price else None,
                    "take_profit_price": str(p.take_profit_price) if p.take_profit_price else None,
                    "max_hold_bars": p.max_hold_bars,
                    "hold_bars": p.hold_bars,
                }
                for p in self.managed_positions.values()
            ],
        }

        with open(filepath, "w") as f:
            json.dump(state, f, indent=2)

        logger.info(f"State saved to {filepath}")

    def load_state(self, filepath: str) -> None:
        """Load order manager state from file."""
        import json
        from pathlib import Path

        if not Path(filepath).exists():
            logger.warning(f"State file not found: {filepath}")
            return

        with open(filepath, "r") as f:
            state = json.load(f)

        self.processed_signals = set(state.get("processed_signals", []))

        for p_state in state.get("positions", []):
            self.managed_positions[p_state["symbol"]] = PositionState(
                symbol=p_state["symbol"],
                entry_date=date.fromisoformat(p_state["entry_date"]),
                entry_price=Decimal(p_state["entry_price"]),
                shares=Decimal(p_state["shares"]),
                stop_loss_price=Decimal(p_state["stop_loss_price"]) if p_state.get("stop_loss_price") else None,
                take_profit_price=Decimal(p_state["take_profit_price"]) if p_state.get("take_profit_price") else None,
                max_hold_bars=p_state.get("max_hold_bars", 60),
                hold_bars=p_state.get("hold_bars", 0),
            )

        logger.info(f"State loaded from {filepath}")
