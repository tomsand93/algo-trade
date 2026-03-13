"""
Strategy-to-Alpaca order bridge.

Responsibilities:
1. Before process_bar(): sync Alpaca fills into strategy state
   - Entry fills: remove from pending_entries, create Fill, append to open_fills
   - Exit fills: remove from pending_exits, create TradeRecord, update realized_pnl
2. After process_bar(): reconcile strategy's desired orders with Alpaca's live orders
   - New strategy order with no Alpaca match -> place order
   - Strategy order price changed -> replace Alpaca order
   - Alpaca order with no strategy match -> cancel it

Uses client_order_id = "bdb_{session_id}_{strategy_order_id}" for tracking.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from .alpaca_broker import AlpacaBroker, STOP_LIMIT_BUFFER_PCT
from .models import Fill, TradeRecord, PendingOrder
from .strategy import StrategyState

log = logging.getLogger(__name__)

# Price tolerance for detecting whether an order needs replacement.
# If prices differ by less than this fraction, skip the replace.
PRICE_TOLERANCE = 0.001  # 0.1%


class OrderManager:
    """Bridges strategy state and Alpaca order book."""

    def __init__(self, broker: AlpacaBroker, strategy: StrategyState,
                 symbol: str, session_id: str):
        self.broker = broker
        self.strategy = strategy
        self.symbol = symbol
        self.session_id = session_id

        # Track last time we checked for fills
        self.last_fill_check: datetime = datetime.now(timezone.utc) - timedelta(hours=1)

        # Map: client_order_id -> alpaca_order_id for active orders
        self.order_id_map: dict[str, str] = {}

    def _client_order_id(self, strategy_order_id: str) -> str:
        return f"bdb_{self.session_id}_{strategy_order_id}"

    def _strategy_order_id_from_client(self, client_order_id: str) -> Optional[str]:
        prefix = f"bdb_{self.session_id}_"
        if client_order_id and client_order_id.startswith(prefix):
            return client_order_id[len(prefix):]
        return None

    # ---- Pre-bar sync: inject Alpaca fills into strategy state ----

    def sync_fills_before_bar(self, bar_index: int):
        """Query Alpaca for filled orders since last check.

        For each fill:
        - Entry fills: remove from strategy.pending_entries, create Fill,
          append to strategy.open_fills, deduct cash
        - Exit fills: remove from strategy.pending_exits, create TradeRecord,
          update strategy.realized_pnl
        """
        now = datetime.now(timezone.utc)
        filled_orders = self.broker.get_filled_orders_since(
            since=self.last_fill_check,
            symbol=self.symbol,
        )
        self.last_fill_check = now

        for order in filled_orders:
            cid = order.client_order_id
            strat_id = self._strategy_order_id_from_client(cid)
            if strat_id is None:
                continue  # Not our order

            fill_price = float(order.filled_avg_price)
            fill_qty = float(order.filled_qty)

            if strat_id.startswith("exit_"):
                # ---- EXIT FILL ----
                self._process_exit_fill(strat_id, fill_price, fill_qty, bar_index)
            else:
                # ---- ENTRY FILL ----
                self._process_entry_fill(strat_id, fill_price, fill_qty, bar_index)

            # Remove from our tracking map
            self.order_id_map.pop(cid, None)

    def _process_entry_fill(self, entry_id: str, fill_price: float,
                            fill_qty: float, bar_index: int):
        """Inject an Alpaca entry fill into strategy state."""
        # Remove from pending entries if present
        if entry_id in self.strategy.pending_entries:
            del self.strategy.pending_entries[entry_id]

        commission = self.strategy._apply_commission(fill_price * fill_qty)
        fill = Fill(
            entry_id=entry_id,
            fill_bar_index=bar_index,
            fill_price=fill_price,
            qty=fill_qty,
            commission=commission,
        )
        self.strategy.open_fills.append(fill)
        self.strategy.cash -= (fill_price * fill_qty + commission)

        log.info("ENTRY FILL synced: %s @ $%.2f qty=%.8f commission=$%.4f",
                 entry_id, fill_price, fill_qty, commission)

    def _process_exit_fill(self, exit_id: str, fill_price: float,
                           fill_qty: float, bar_index: int):
        """Inject an Alpaca exit fill into strategy state."""
        # Remove from pending exits if present
        if exit_id in self.strategy.pending_exits:
            exit_order = self.strategy.pending_exits.pop(exit_id)
            from_entry = exit_order.from_entry
        else:
            # Derive entry_id from exit_id (e.g. "exit_entry1" -> "entry1")
            from_entry = exit_id.replace("exit_", "", 1)

        # Find matching open fill
        matching_fill = None
        for f in self.strategy.open_fills:
            if f.entry_id == from_entry:
                matching_fill = f
                break

        if matching_fill is None:
            log.warning("Exit fill for %s but no matching open fill found", exit_id)
            return

        trade_value = fill_price * matching_fill.qty
        commission = self.strategy._apply_commission(trade_value)
        pnl_gross = (fill_price - matching_fill.fill_price) * matching_fill.qty
        commission_total = matching_fill.commission + commission

        trade = TradeRecord(
            entry_id=matching_fill.entry_id,
            entry_bar_index=matching_fill.fill_bar_index,
            entry_price=matching_fill.fill_price,
            entry_qty=matching_fill.qty,
            exit_bar_index=bar_index,
            exit_price=fill_price,
            pnl_gross=pnl_gross,
            commission_total=commission_total,
            pnl_net=pnl_gross - commission_total,
        )
        self.strategy.closed_trades.append(trade)
        self.strategy.realized_pnl += trade.pnl_net
        self.strategy.cash += (trade_value - commission)
        self.strategy.open_fills.remove(matching_fill)

        log.info("EXIT FILL synced: %s @ $%.2f pnl_net=$%.4f",
                 exit_id, fill_price, trade.pnl_net)

    # ---- Post-bar sync: reconcile strategy orders with Alpaca ----

    def sync_orders_after_bar(self):
        """Reconcile strategy's pending orders with Alpaca's live orders.

        For each strategy pending order:
          - If no Alpaca order exists -> place it
          - If Alpaca order exists but price differs -> replace it
        For each Alpaca order with no strategy match -> cancel it
        """
        alpaca_orders = self.broker.get_open_orders(symbol=self.symbol)

        # Build map of client_order_id -> alpaca_order for our session's orders
        alpaca_by_strat_id: dict[str, object] = {}
        orphan_orders = []
        for ao in alpaca_orders:
            strat_id = self._strategy_order_id_from_client(ao.client_order_id)
            if strat_id is not None:
                alpaca_by_strat_id[strat_id] = ao
            elif ao.client_order_id and ao.client_order_id.startswith("bdb_"):
                # Order from a previous session — treat as orphan
                orphan_orders.append(ao)

        # ---- Sync entry orders ----
        for strat_id, pending in self.strategy.pending_entries.items():
            cid = self._client_order_id(strat_id)
            existing = alpaca_by_strat_id.pop(strat_id, None)

            if existing is None:
                # Place new order
                order = self.broker.place_stop_limit_buy(
                    symbol=self.symbol,
                    qty=pending.qty,
                    stop_price=pending.price,
                    client_order_id=cid,
                )
                self.order_id_map[cid] = str(order.id)
            else:
                # Check if price changed enough to warrant replacement
                existing_stop = float(existing.stop_price) if existing.stop_price else 0
                if abs(existing_stop - pending.price) / max(pending.price, 1e-8) > PRICE_TOLERANCE:
                    limit_price = round(pending.price * (1 + STOP_LIMIT_BUFFER_PCT / 100), 2)
                    self.broker.replace_order(
                        order_id=str(existing.id),
                        qty=pending.qty,
                        stop_price=pending.price,
                        limit_price=limit_price,
                    )
                    log.info("Replaced entry order %s: stop $%.2f -> $%.2f",
                             strat_id, existing_stop, pending.price)
                # Mark as seen
                self.order_id_map[cid] = str(existing.id)

        # ---- Sync exit orders ----
        for strat_id, pending in self.strategy.pending_exits.items():
            cid = self._client_order_id(strat_id)
            existing = alpaca_by_strat_id.pop(strat_id, None)

            if existing is None:
                # Place new exit order
                order = self.broker.place_limit_sell(
                    symbol=self.symbol,
                    qty=pending.qty,
                    limit_price=pending.price,
                    client_order_id=cid,
                )
                self.order_id_map[cid] = str(order.id)
            else:
                # Check if limit price changed
                existing_limit = float(existing.limit_price) if existing.limit_price else 0
                if abs(existing_limit - pending.price) / max(pending.price, 1e-8) > PRICE_TOLERANCE:
                    self.broker.replace_order(
                        order_id=str(existing.id),
                        qty=pending.qty,
                        limit_price=pending.price,
                    )
                    log.info("Replaced exit order %s: limit $%.2f -> $%.2f",
                             strat_id, existing_limit, pending.price)
                self.order_id_map[cid] = str(existing.id)

        # ---- Cancel Alpaca orders that strategy no longer wants ----
        # Remaining in alpaca_by_strat_id are orders not matched by strategy
        for strat_id, ao in alpaca_by_strat_id.items():
            log.info("Cancelling stale order %s (Alpaca ID %s)", strat_id, ao.id)
            try:
                self.broker.cancel_order(str(ao.id))
            except Exception as e:
                log.warning("Failed to cancel stale order %s: %s", ao.id, e)

        # Cancel orphan orders from previous sessions
        for ao in orphan_orders:
            log.info("Cancelling orphan order from previous session: %s", ao.client_order_id)
            try:
                self.broker.cancel_order(str(ao.id))
            except Exception as e:
                log.warning("Failed to cancel orphan order %s: %s", ao.id, e)

    def cancel_all_entries(self):
        """Cancel all entry orders on Alpaca (e.g. when risk engine disables)."""
        alpaca_orders = self.broker.get_open_orders(symbol=self.symbol)
        for ao in alpaca_orders:
            strat_id = self._strategy_order_id_from_client(ao.client_order_id)
            if strat_id and not strat_id.startswith("exit_"):
                try:
                    self.broker.cancel_order(str(ao.id))
                    log.info("Cancelled entry order %s due to risk disable", strat_id)
                except Exception as e:
                    log.warning("Failed to cancel entry %s: %s", strat_id, e)

    def get_newly_closed_trades(self, prev_count: int) -> list[TradeRecord]:
        """Return trades closed since prev_count."""
        return self.strategy.closed_trades[prev_count:]
