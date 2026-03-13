"""
Live paper trading bot orchestrator for BDB DCA strategy.

Startup:
  1. Connect to Alpaca broker
  2. Fetch warmup bars (90 days of 30m bars)
  3. Replay indicators + strategy through warmup history

Main loop (poll every 15 seconds):
  1. Check if a new 30m bar has completed
  2. Fetch completed bar from Alpaca
  3. Sync Alpaca fills into strategy state (order_manager.sync_fills_before_bar)
  4. Update indicators
  5. Run risk engine checks
  6. Run strategy.process_bar()
  7. Report closed trades to risk engine
  8. Reconcile orders with Alpaca (order_manager.sync_orders_after_bar)
  9. Log status, save state to JSON

Graceful shutdown (SIGINT/SIGTERM):
  - Cancel pending entry orders (keep exit orders alive)
  - Save state to disk
"""

import json
import logging
import signal
import time
import uuid
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

from .alpaca_broker import AlpacaBroker
from .config import StrategyConfig
from .indicators import IndicatorState
from .live_data import fetch_warmup_bars, get_last_completed_bar
from .models import Bar
from .order_manager import OrderManager
from .risk import RiskConfig, RiskEngine
from .strategy import StrategyState

log = logging.getLogger(__name__)

POLL_INTERVAL = 15  # seconds between checks
HEARTBEAT_INTERVAL = 60  # seconds between status logs
STATE_FILE = "bdb_dca_state.json"
BAR_DURATION_MS = 30 * 60 * 1000  # 30 minutes in ms


class LiveBot:
    """Main orchestrator for live paper trading."""

    def __init__(self, config: StrategyConfig,
                 risk_config: Optional[RiskConfig] = None,
                 dry_run: bool = False):
        self.config = config
        self.risk_config = risk_config
        self.dry_run = dry_run

        self.session_id = uuid.uuid4().hex[:8]
        self.broker = AlpacaBroker()
        self.indicators: Optional[IndicatorState] = None
        self.strategy: Optional[StrategyState] = None
        self.risk_engine: Optional[RiskEngine] = None
        self.order_manager: Optional[OrderManager] = None

        self.last_bar_timestamp: Optional[int] = None
        self.bar_index: int = 0
        self.running: bool = False
        self.last_heartbeat: float = 0

    def start(self):
        """Full startup sequence: connect, warmup, then enter main loop."""
        log.info("=" * 60)
        log.info("BDB DCA Live Bot starting (session=%s, dry_run=%s)",
                 self.session_id, self.dry_run)
        log.info("Config: symbol=%s, commission=%.2f%%, capital=$%.0f",
                 self.config.symbol, self.config.commission_pct,
                 self.config.initial_capital)
        log.info("=" * 60)

        # Connect to Alpaca
        acct = self.broker.connect()
        log.info("Account equity: $%s, buying_power: $%s", acct.equity, acct.buying_power)

        # Override strategy capital to match Alpaca account equity
        actual_equity = float(acct.equity)
        if abs(actual_equity - self.config.initial_capital) > 1.0:
            log.info("Overriding initial_capital from $%.0f to Alpaca equity $%.2f",
                     self.config.initial_capital, actual_equity)
            self.config.initial_capital = actual_equity

        # Initialize components
        self.indicators = IndicatorState(
            jaw_length=self.config.jaw_length,
            jaw_offset=self.config.jaw_offset,
            teeth_length=self.config.teeth_length,
            teeth_offset=self.config.teeth_offset,
            lips_length=self.config.lips_length,
            lips_offset=self.config.lips_offset,
            atr_length=self.config.atr_length,
            lowest_bars=self.config.lowest_bars,
        )
        self.strategy = StrategyState(self.config)

        if self.risk_config is not None:
            self.risk_engine = RiskEngine(self.risk_config)

        self.order_manager = OrderManager(
            broker=self.broker,
            strategy=self.strategy,
            symbol=self.config.symbol,
            session_id=self.session_id,
        )

        # Warmup: replay historical bars through indicators + strategy
        self._warmup()

        if self.dry_run:
            log.info("DRY RUN complete. Indicators initialized. Exiting.")
            self._log_indicator_status()
            return

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown_handler)
        signal.signal(signal.SIGTERM, self._shutdown_handler)

        # Enter main loop
        self.running = True
        self._main_loop()

    def _warmup(self):
        """Fetch historical bars and replay through indicators + strategy."""
        bars = fetch_warmup_bars(symbol=self.config.symbol, days=90)
        if not bars:
            raise RuntimeError("No warmup bars fetched — cannot initialize indicators")

        log.info("Replaying %d warmup bars through indicators and strategy...", len(bars))

        for i, bar in enumerate(bars):
            self.indicators.update(bar)
            # During warmup, process_bar runs but we don't send real orders.
            # in_window=False suppresses new entry signals (just like backtest warmup).
            risk_can_enter = True
            if self.risk_engine is not None:
                self.risk_engine.on_bar(
                    bar.timestamp, self.strategy.equity,
                    self.indicators.atr_value, bar.close,
                )
                risk_can_enter = self.risk_engine.can_enter()
                if self.risk_engine.just_disabled():
                    self.strategy.pending_entries.clear()

            prev_closed = len(self.strategy.closed_trades)
            self.strategy.process_bar(i, bar, self.indicators,
                                      in_trading_window=False,
                                      risk_can_enter=risk_can_enter)

            if self.risk_engine is not None:
                for trade in self.strategy.closed_trades[prev_closed:]:
                    self.risk_engine.on_trade_closed(trade, bar.timestamp)

        self.bar_index = len(bars)
        self.last_bar_timestamp = bars[-1].timestamp if bars else None

        log.info("Warmup complete. bar_index=%d, last_bar=%s",
                 self.bar_index,
                 datetime.fromtimestamp(self.last_bar_timestamp / 1000, tz=timezone.utc).isoformat()
                 if self.last_bar_timestamp else "N/A")
        self._log_indicator_status()

        # Clear any pending orders from warmup replay — they were simulated
        self.strategy.pending_entries.clear()
        self.strategy.pending_exits.clear()
        self.strategy.open_fills.clear()
        self.strategy.cash = self.config.initial_capital
        self.strategy.realized_pnl = 0.0
        self.strategy.closed_trades.clear()
        self.strategy.equity = self.config.initial_capital
        self.strategy.current_layer = 0

    def _main_loop(self):
        """Poll for new bars and process them."""
        log.info("Entering main loop (poll every %ds)...", POLL_INTERVAL)

        while self.running:
            try:
                self._tick()
            except Exception as e:
                log.error("Error in main loop tick: %s", e, exc_info=True)

            time.sleep(POLL_INTERVAL)

    def _tick(self):
        """Single iteration of the main loop."""
        now = time.time()

        # Heartbeat logging
        if now - self.last_heartbeat >= HEARTBEAT_INTERVAL:
            self._log_heartbeat()
            self.last_heartbeat = now

        # Check for new completed bar
        bar = get_last_completed_bar(symbol=self.config.symbol)
        if bar is None:
            return

        if self.last_bar_timestamp is not None and bar.timestamp <= self.last_bar_timestamp:
            return  # Already processed this bar

        log.info("--- New bar: %s | O=%.2f H=%.2f L=%.2f C=%.2f V=%.2f ---",
                 datetime.fromtimestamp(bar.timestamp / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                 bar.open, bar.high, bar.low, bar.close, bar.volume)

        self._process_bar(bar)

    def _process_bar(self, bar: Bar):
        """Full bar processing pipeline."""
        prev_closed_count = len(self.strategy.closed_trades)

        # Step 1: Sync Alpaca fills into strategy state
        self.order_manager.sync_fills_before_bar(self.bar_index)

        # Step 2: Update indicators
        self.indicators.update(bar)

        # Step 3: Risk engine
        risk_can_enter = True
        if self.risk_engine is not None:
            self.risk_engine.on_bar(
                bar.timestamp, self.strategy.equity,
                self.indicators.atr_value, bar.close,
            )
            risk_can_enter = self.risk_engine.can_enter()

            if self.risk_engine.just_disabled():
                self.strategy.pending_entries.clear()
                self.order_manager.cancel_all_entries()

        # Step 4: Run strategy
        self.strategy.process_bar(
            self.bar_index, bar, self.indicators,
            in_trading_window=True,
            risk_can_enter=risk_can_enter,
        )

        # Step 5: Report newly closed trades to risk engine
        if self.risk_engine is not None:
            for trade in self.strategy.closed_trades[prev_closed_count:]:
                self.risk_engine.on_trade_closed(trade, bar.timestamp)
                log.info("Trade closed: %s entry=$%.2f exit=$%.2f pnl=$%.4f",
                         trade.entry_id, trade.entry_price,
                         trade.exit_price, trade.pnl_net)

        # Also log newly closed trades when no risk engine
        if self.risk_engine is None:
            for trade in self.strategy.closed_trades[prev_closed_count:]:
                log.info("Trade closed: %s entry=$%.2f exit=$%.2f pnl=$%.4f",
                         trade.entry_id, trade.entry_price,
                         trade.exit_price, trade.pnl_net)

        # Step 6: Sync strategy orders to Alpaca
        self.order_manager.sync_orders_after_bar()

        # Step 7: Update tracking
        self.last_bar_timestamp = bar.timestamp
        self.bar_index += 1

        # Step 8: Log and save state
        self._log_bar_status(bar)
        self._save_state()

    def _log_indicator_status(self):
        ind = self.indicators
        log.info("Indicators: ATR=%.4f, Jaw=%.4f, Teeth=%.4f, Lips=%.4f, AO=%.4f",
                 ind.atr_value or 0,
                 ind.jaw or 0,
                 ind.teeth or 0,
                 ind.lips or 0,
                 ind.ao_value or 0)

    def _log_bar_status(self, bar: Bar):
        s = self.strategy
        log.info("Status: equity=$%.2f, cash=$%.2f, open_fills=%d, "
                 "layer=%d, pending_entries=%d, pending_exits=%d, "
                 "realized_pnl=$%.4f",
                 s.equity, s.cash, len(s.open_fills),
                 s.current_layer, len(s.pending_entries),
                 len(s.pending_exits), s.realized_pnl)

        if s.take_profit_level:
            log.info("  TP level: $%.2f", s.take_profit_level)
        if s.bull_bar_confirmation_level:
            log.info("  Confirmation level: $%.2f", s.bull_bar_confirmation_level)

        if self.risk_engine:
            re = self.risk_engine
            log.info("  Risk: state=%s, can_enter=%s, suppressed=%s",
                     re.state, re.can_enter(), re.entry_suppressed)

    def _log_heartbeat(self):
        try:
            pos = self.broker.get_btc_position()
            acct = self.broker.get_account()
            pos_info = (f"qty={pos.qty}, avg_entry=${pos.avg_entry_price}, "
                        f"unrealized_pl=${pos.unrealized_pl}"
                        if pos else "FLAT")
            log.info("HEARTBEAT: alpaca_equity=$%s, position=%s, "
                     "strategy_equity=$%.2f, open_fills=%d, bar_index=%d",
                     acct.equity, pos_info,
                     self.strategy.equity if self.strategy else 0,
                     len(self.strategy.open_fills) if self.strategy else 0,
                     self.bar_index)
        except Exception as e:
            log.warning("Heartbeat failed: %s", e)

    def _save_state(self):
        """Persist bot state to JSON for crash recovery."""
        state = {
            "session_id": self.session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "bar_index": self.bar_index,
            "last_bar_timestamp": self.last_bar_timestamp,
            "strategy": {
                "equity": self.strategy.equity,
                "cash": self.strategy.cash,
                "realized_pnl": self.strategy.realized_pnl,
                "current_layer": self.strategy.current_layer,
                "open_fills": [
                    {
                        "entry_id": f.entry_id,
                        "fill_bar_index": f.fill_bar_index,
                        "fill_price": f.fill_price,
                        "qty": f.qty,
                        "commission": f.commission,
                    }
                    for f in self.strategy.open_fills
                ],
                "pending_entries": {
                    k: {"price": v.price, "qty": v.qty}
                    for k, v in self.strategy.pending_entries.items()
                },
                "pending_exits": {
                    k: {"price": v.price, "qty": v.qty, "from_entry": v.from_entry}
                    for k, v in self.strategy.pending_exits.items()
                },
                "total_closed_trades": len(self.strategy.closed_trades),
                "bull_bar_confirmation_level": self.strategy.bull_bar_confirmation_level,
                "bull_bar_invalidation_level": self.strategy.bull_bar_invalidation_level,
                "take_profit_level": self.strategy.take_profit_level,
            },
        }
        if self.risk_engine:
            state["risk"] = {
                "state": self.risk_engine.state,
                "can_enter": self.risk_engine.can_enter(),
                "entry_suppressed": self.risk_engine.entry_suppressed,
                "consecutive_losses": self.risk_engine.consecutive_losses,
                "events_count": len(self.risk_engine.events),
            }

        try:
            path = Path(STATE_FILE)
            path.write_text(json.dumps(state, indent=2, default=str))
            log.debug("State saved to %s", STATE_FILE)
        except Exception as e:
            log.warning("Failed to save state: %s", e)

    def _shutdown_handler(self, signum, frame):
        """Graceful shutdown: cancel entry orders, keep exits, save state."""
        log.info("Shutdown signal received (sig=%s). Cleaning up...", signum)
        self.running = False

        try:
            # Cancel entry orders but keep exit orders alive
            if self.order_manager:
                self.order_manager.cancel_all_entries()
                log.info("Entry orders cancelled. Exit orders left active.")

            # Save final state
            if self.strategy:
                self._save_state()
                log.info("State saved.")
        except Exception as e:
            log.error("Error during shutdown: %s", e)

        log.info("Shutdown complete.")
