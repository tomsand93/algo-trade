"""
Live stock trading bot orchestrator for BDB DCA strategy.

Startup:
  1. Connect to Alpaca broker
  2. Fetch warmup bars (90 days of 30m bars, market hours only)
  3. Replay indicators + strategy through warmup history

Main loop (poll every 15 seconds):
  1. Check if market is open (9:30 AM - 4:00 PM ET)
  2. Check if a new 30m bar has completed
  3. Fetch completed bar from Alpaca
  4. Sync Alpaca fills into strategy state (order_manager.sync_fills_before_bar)
  5. Update indicators
  6. Run risk engine checks
  7. Run strategy.process_bar()
  8. Report closed trades to risk engine
  9. Reconcile orders with Alpaca (order_manager.sync_orders_after_bar)
  10. Log status, save state to JSON

Graceful shutdown (SIGINT/SIGTERM):
  - Cancel pending entry orders (keep exit orders alive)
  - Save state to disk
"""

import csv
import json
import logging
import signal
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .alpaca_broker import AlpacaBroker
from .config import StrategyConfig
from .indicators import IndicatorState
from .models import Bar, TradeRecord
from .order_manager import OrderManager
from .risk import RiskConfig, RiskEngine
from .stock_live_data import (
    fetch_stock_warmup_bars,
    get_last_completed_stock_bar,
    is_market_open,
    get_next_market_open,
)
from .strategy import StrategyState

log = logging.getLogger(__name__)

POLL_INTERVAL = 15  # seconds between checks
HEARTBEAT_INTERVAL = 60  # seconds between status logs
BAR_DURATION_MS = 30 * 60 * 1000  # 30 minutes in ms

# Directories for logs and data
LOGS_DIR = Path("logs")
DATA_DIR = Path("data")


class StockTradeLogger:
    """Handles trade event logging and CSV tracking for stocks."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self._ensure_dirs()

        # Log file: logs/stock_trades_{symbol}_{date}.log
        date_str = datetime.now().strftime("%Y-%m-%d")
        self.log_file = LOGS_DIR / f"stock_trades_{symbol}_{date_str}.log"

        # CSV file: data/stock_trades_{symbol}.csv
        self.csv_file = DATA_DIR / f"stock_trades_{symbol}.csv"
        self._init_csv()

    def _ensure_dirs(self):
        LOGS_DIR.mkdir(exist_ok=True)
        DATA_DIR.mkdir(exist_ok=True)

    def _init_csv(self):
        """Initialize CSV file with headers if it doesn't exist."""
        if not self.csv_file.exists():
            with open(self.csv_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'symbol', 'entry_id', 'entry_time', 'entry_price',
                    'entry_qty', 'exit_time', 'exit_price', 'pnl_gross',
                    'commission', 'pnl_net', 'bars_held'
                ])

    def _log_event(self, event_type: str, message: str):
        """Write a line to the trade log file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{timestamp} [{event_type}] {self.symbol} {message}\n"
        with open(self.log_file, 'a') as f:
            f.write(line)

    def log_signal(self, signal_type: str, confirm_price: float, layer: int):
        self._log_event("SIGNAL", f"{signal_type} confirm=${confirm_price:.2f} layer={layer}")

    def log_order_entry(self, entry_id: str, qty: float, stop_price: float):
        self._log_event("ORDER", f"ENTRY {entry_id} STOP_BUY qty={qty:.4f} stop=${stop_price:.2f}")

    def log_order_exit(self, exit_id: str, qty: float, limit_price: float):
        self._log_event("ORDER", f"EXIT {exit_id} LIMIT_SELL qty={qty:.4f} limit=${limit_price:.2f}")

    def log_fill_entry(self, entry_id: str, qty: float, price: float, commission: float):
        self._log_event("FILL", f"ENTRY {entry_id} qty={qty:.4f} price=${price:.2f} commission=${commission:.2f}")

    def log_fill_exit(self, exit_id: str, qty: float, price: float, pnl: float):
        self._log_event("FILL", f"EXIT {exit_id} qty={qty:.4f} price=${price:.2f} pnl=${pnl:.2f}")

    def record_closed_trade(self, trade: TradeRecord):
        """Append a closed trade to the CSV file."""
        with open(self.csv_file, 'a', newline='') as f:
            writer = csv.writer(f)
            bars_held = trade.exit_bar_index - trade.entry_bar_index
            writer.writerow([
                datetime.now().isoformat(),
                self.symbol,
                trade.entry_id,
                trade.entry_bar_index,
                f"{trade.entry_price:.2f}",
                f"{trade.entry_qty:.4f}",
                trade.exit_bar_index,
                f"{trade.exit_price:.2f}",
                f"{trade.pnl_gross:.2f}",
                f"{trade.commission_total:.2f}",
                f"{trade.pnl_net:.2f}",
                bars_held
            ])


class StockLiveBot:
    """Main orchestrator for live stock trading."""

    def __init__(self, config: StrategyConfig,
                 risk_config: Optional[RiskConfig] = None,
                 dry_run: bool = False,
                 paper: bool = True):
        self.config = config
        self.risk_config = risk_config
        self.dry_run = dry_run
        self.paper = paper
        self.symbol = config.symbol

        self.session_id = uuid.uuid4().hex[:8]
        self.broker = AlpacaBroker()
        self.indicators: Optional[IndicatorState] = None
        self.strategy: Optional[StrategyState] = None
        self.risk_engine: Optional[RiskEngine] = None
        self.order_manager: Optional[OrderManager] = None
        self.trade_logger: Optional[StockTradeLogger] = None

        self.last_bar_timestamp: Optional[int] = None
        self.bar_index: int = 0
        self.running: bool = False
        self.last_heartbeat: float = 0

        # State file: bdb_dca_stock_{symbol}_state.json
        self.state_file = f"bdb_dca_stock_{self.symbol}_state.json"

    def start(self):
        """Full startup sequence: connect, warmup, then enter main loop."""
        log.info("=" * 60)
        log.info("BDB DCA Stock Live Bot starting (session=%s, dry_run=%s, paper=%s)",
                 self.session_id, self.dry_run, self.paper)
        log.info("Config: symbol=%s, commission=%.2f%%, capital=$%.0f",
                 self.symbol, self.config.commission_pct,
                 self.config.initial_capital)
        log.info("=" * 60)

        # Connect to Alpaca
        self._connect_broker()

        # Initialize trade logger
        self.trade_logger = StockTradeLogger(self.symbol)

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
            symbol=self.symbol,
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

    def _connect_broker(self):
        """Connect to Alpaca with paper/live mode."""
        # The AlpacaBroker currently defaults to paper=True.
        # For live trading, we'd need to modify the broker or pass a flag.
        # For now, we just connect and log the mode.
        acct = self.broker.connect()
        mode = "PAPER" if self.paper else "LIVE"
        log.info("[%s] Account equity: $%s, buying_power: $%s",
                 mode, acct.equity, acct.buying_power)

        # Override strategy capital to match Alpaca account equity
        actual_equity = float(acct.equity)
        if abs(actual_equity - self.config.initial_capital) > 1.0:
            log.info("Overriding initial_capital from $%.0f to Alpaca equity $%.2f",
                     self.config.initial_capital, actual_equity)
            self.config.initial_capital = actual_equity

    def _warmup(self):
        """Fetch historical bars and replay through indicators + strategy."""
        bars = fetch_stock_warmup_bars(symbol=self.symbol, days=90)
        if not bars:
            raise RuntimeError(f"No warmup bars fetched for {self.symbol} — cannot initialize indicators")

        log.info("[%s] Replaying %d warmup bars through indicators and strategy...",
                 self.symbol, len(bars))

        for i, bar in enumerate(bars):
            self.indicators.update(bar)
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

        log.info("[%s] Warmup complete. bar_index=%d, last_bar=%s",
                 self.symbol, self.bar_index,
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
        log.info("[%s] Entering main loop (poll every %ds)...", self.symbol, POLL_INTERVAL)

        while self.running:
            try:
                self._tick()
            except Exception as e:
                log.error("[%s] Error in main loop tick: %s", self.symbol, e, exc_info=True)

            time.sleep(POLL_INTERVAL)

    def _tick(self):
        """Single iteration of the main loop."""
        now = time.time()

        # Heartbeat logging
        if now - self.last_heartbeat >= HEARTBEAT_INTERVAL:
            self._log_heartbeat()
            self.last_heartbeat = now

        # Check if market is open
        if not is_market_open():
            next_open = get_next_market_open()
            # Only log once per minute to avoid spam
            if int(now) % 60 == 0:
                log.debug("[%s] Market closed. Next open: %s",
                          self.symbol, next_open.strftime("%Y-%m-%d %H:%M ET"))
            return

        # Check for new completed bar
        bar = get_last_completed_stock_bar(symbol=self.symbol)
        if bar is None:
            return

        if self.last_bar_timestamp is not None and bar.timestamp <= self.last_bar_timestamp:
            return  # Already processed this bar

        log.info("[%s] --- New bar: %s | O=%.2f H=%.2f L=%.2f C=%.2f V=%.0f ---",
                 self.symbol,
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

        # Step 5: Report newly closed trades to risk engine and log them
        for trade in self.strategy.closed_trades[prev_closed_count:]:
            if self.risk_engine is not None:
                self.risk_engine.on_trade_closed(trade, bar.timestamp)

            log.info("[%s] Trade closed: %s entry=$%.2f exit=$%.2f pnl=$%.2f",
                     self.symbol, trade.entry_id, trade.entry_price,
                     trade.exit_price, trade.pnl_net)

            # Log to CSV
            if self.trade_logger:
                self.trade_logger.record_closed_trade(trade)
                self.trade_logger.log_fill_exit(
                    f"exit_{trade.entry_id}", trade.entry_qty,
                    trade.exit_price, trade.pnl_net
                )

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
        log.info("[%s] Indicators: ATR=%.4f, Jaw=%.4f, Teeth=%.4f, Lips=%.4f, AO=%.4f",
                 self.symbol,
                 ind.atr_value or 0,
                 ind.jaw or 0,
                 ind.teeth or 0,
                 ind.lips or 0,
                 ind.ao_value or 0)

    def _log_bar_status(self, bar: Bar):
        s = self.strategy
        log.info("[%s] Status: equity=$%.2f, cash=$%.2f, open_fills=%d, "
                 "layer=%d, pending_entries=%d, pending_exits=%d, "
                 "realized_pnl=$%.2f",
                 self.symbol,
                 s.equity, s.cash, len(s.open_fills),
                 s.current_layer, len(s.pending_entries),
                 len(s.pending_exits), s.realized_pnl)

        if s.take_profit_level:
            log.info("[%s]   TP level: $%.2f", self.symbol, s.take_profit_level)
        if s.bull_bar_confirmation_level:
            log.info("[%s]   Confirmation level: $%.2f", self.symbol, s.bull_bar_confirmation_level)

        if self.risk_engine:
            re = self.risk_engine
            log.info("[%s]   Risk: state=%s, can_enter=%s, suppressed=%s",
                     self.symbol, re.state, re.can_enter(), re.entry_suppressed)

    def _log_heartbeat(self):
        try:
            pos = self.broker.get_stock_position(self.symbol)
            acct = self.broker.get_account()
            pos_info = (f"qty={pos.qty}, avg_entry=${pos.avg_entry_price}, "
                        f"unrealized_pl=${pos.unrealized_pl}"
                        if pos else "FLAT")
            log.info("[%s] HEARTBEAT: alpaca_equity=$%s, position=%s, "
                     "strategy_equity=$%.2f, open_fills=%d, bar_index=%d",
                     self.symbol,
                     acct.equity, pos_info,
                     self.strategy.equity if self.strategy else 0,
                     len(self.strategy.open_fills) if self.strategy else 0,
                     self.bar_index)
        except Exception as e:
            log.warning("[%s] Heartbeat failed: %s", self.symbol, e)

    def _save_state(self):
        """Persist bot state to JSON for crash recovery."""
        state = {
            "session_id": self.session_id,
            "symbol": self.symbol,
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
            path = Path(self.state_file)
            path.write_text(json.dumps(state, indent=2, default=str))
            log.debug("[%s] State saved to %s", self.symbol, self.state_file)
        except Exception as e:
            log.warning("[%s] Failed to save state: %s", self.symbol, e)

    def _shutdown_handler(self, signum, frame):
        """Graceful shutdown: cancel entry orders, keep exits, save state."""
        log.info("[%s] Shutdown signal received (sig=%s). Cleaning up...", self.symbol, signum)
        self.running = False

        try:
            # Cancel entry orders but keep exit orders alive
            if self.order_manager:
                self.order_manager.cancel_all_entries()
                log.info("[%s] Entry orders cancelled. Exit orders left active.", self.symbol)

            # Save final state
            if self.strategy:
                self._save_state()
                log.info("[%s] State saved.", self.symbol)
        except Exception as e:
            log.error("[%s] Error during shutdown: %s", self.symbol, e)

        log.info("[%s] Shutdown complete.", self.symbol)
