"""
Stock strategy state machine with ATR-based stop loss.

Copy of strategy.py with these additions:
- Stop loss: avg_entry_price - stoploss_atr_mult × ATR (closes ALL fills at once)
- Take profit multiplier is configurable (default 3× ATR instead of 2×)

Per-bar execution:
1. Process pending stop entries (fill if high >= stop price)
2. Process pending limit exits (fill if high >= limit price)
2b. Process stop loss (if low <= SL level, close ALL fills)
3. Update equity (cash + unrealized PnL)
4. Run strategy logic: signals, crossover, layers, order placement
5. Save state for next bar

SL fill model:
- If bar opens below SL (gap down): fill at open - slippage
- Otherwise: fill at stoploss_level - slippage
"""

import math
from typing import Optional
from .config import StrategyConfig
from .models import PendingOrder, Fill, TradeRecord


class StockStrategyState:
    def __init__(self, config: StrategyConfig,
                 stoploss_atr_mult: float = 1.5,
                 takeprofit_atr_mult: float = 3.0):
        self.config = config
        self.slippage = config.slippage
        self.stoploss_atr_mult = stoploss_atr_mult
        self.takeprofit_atr_mult = takeprofit_atr_mult

        # Capital
        self.initial_capital = config.initial_capital
        self.cash = config.initial_capital
        self.equity = config.initial_capital
        self.realized_pnl = 0.0  # running sum of closed trade net PnL

        # Position tracking
        self.open_fills: list[Fill] = []  # currently open entry fills
        self.closed_trades: list[TradeRecord] = []

        # Pending orders
        self.pending_entries: dict[str, PendingOrder] = {}
        self.pending_exits: dict[str, PendingOrder] = {}

        # Strategy vars (matching Pine var declarations)
        self.bull_bar_confirmation_level: Optional[float] = None
        self.bull_bar_invalidation_level: Optional[float] = None
        self.take_profit_level: Optional[float] = None
        self.stoploss_level: Optional[float] = None
        self.is_true_bullish_reversal_bar: bool = False

        self.layer1: Optional[float] = None
        self.layer2_threshold: Optional[float] = None
        self.layer3_threshold: Optional[float] = None
        self.layer4_threshold: Optional[float] = None
        self.current_layer: int = 0

        # Previous bar values for crossover/crossunder
        self.prev_high: Optional[float] = None
        self.prev_low: Optional[float] = None
        self.prev_confirm: Optional[float] = None
        self.prev_invalid: Optional[float] = None

        # Track opentrades for layer detection
        self.prev_opentrades: int = 0

        # Equity tracking
        self.peak_equity = config.initial_capital
        self.max_drawdown = 0.0
        self.equity_curve: list = []

        # SL tracking
        self.sl_exits: int = 0  # count of stop-loss triggered exits

    @property
    def opentrades(self) -> int:
        return len(self.open_fills)

    @property
    def position_size(self) -> float:
        return sum(f.qty for f in self.open_fills)

    @property
    def position_avg_price(self) -> float:
        if not self.open_fills:
            return 0.0
        total_cost = sum(f.fill_price * f.qty for f in self.open_fills)
        total_qty = sum(f.qty for f in self.open_fills)
        return total_cost / total_qty if total_qty > 0 else 0.0

    def _compute_equity(self, current_price: float) -> float:
        """Match Pine: strategy.equity = initial_capital + netprofit + openprofit."""
        unrealized = sum(
            (current_price - f.fill_price) * f.qty
            for f in self.open_fills
        )
        return self.initial_capital + self.realized_pnl + unrealized

    def _apply_commission(self, trade_value: float) -> float:
        return trade_value * self.config.commission_pct / 100.0

    def _get_layer_equity_qty(self, mult: float, layer: int, price: float) -> float:
        """Match Pine's getLayerEquityQty exactly."""
        sum_w = 1.0 + mult + mult ** 2 + mult ** 3
        w_cur = mult ** layer
        pct = w_cur / sum_w
        cap = self.equity * pct
        qty = cap / price
        return qty

    def process_bar(self, bar_index: int, bar, indicators,
                    in_trading_window: bool, risk_can_enter: bool = True):
        """
        Process a single bar through the strategy.

        Args:
            bar_index: index into the bars array
            bar: Bar object
            indicators: IndicatorState (already updated for this bar)
            in_trading_window: whether current bar is within start/stop dates
            risk_can_enter: False when risk engine has disabled entries
        """
        o, h, l, c = bar.open, bar.high, bar.low, bar.close

        # ============================================================
        # STEP 1: Process pending STOP ENTRIES
        # ============================================================
        entries_to_remove = []
        for oid, order in list(self.pending_entries.items()):
            if order.order_type == 'stop' and order.direction == 'long':
                # Stop buy triggers when high >= stop price
                if h >= order.price:
                    # Fill price: if open >= stop, fill at open; else at stop
                    if o >= order.price:
                        fill_price = o + self.slippage
                    else:
                        fill_price = order.price + self.slippage

                    qty = order.qty
                    trade_value = fill_price * qty
                    commission = self._apply_commission(trade_value)

                    fill = Fill(
                        entry_id=oid,
                        fill_bar_index=bar_index,
                        fill_price=fill_price,
                        qty=qty,
                        commission=commission
                    )
                    self.open_fills.append(fill)
                    self.cash -= (trade_value + commission)
                    entries_to_remove.append(oid)

        for oid in entries_to_remove:
            del self.pending_entries[oid]

        # ============================================================
        # STEP 2: Process pending LIMIT EXITS (take profit)
        # ============================================================
        exits_to_remove = []
        fills_to_close = []
        for oid, order in list(self.pending_exits.items()):
            if order.order_type == 'limit' and order.direction == 'long':
                # Limit sell triggers when high >= limit price
                if order.price is not None and h >= order.price:
                    # Fill price (no slippage on limit orders per Pine)
                    if o >= order.price:
                        fill_price = o
                    else:
                        fill_price = order.price

                    # Find the matching entry fill
                    matching_fill = None
                    for f in self.open_fills:
                        if f.entry_id == order.from_entry:
                            matching_fill = f
                            break

                    if matching_fill:
                        trade_value = fill_price * matching_fill.qty
                        commission = self._apply_commission(trade_value)

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
                            pnl_net=pnl_gross - commission_total
                        )
                        self.closed_trades.append(trade)
                        self.realized_pnl += trade.pnl_net
                        fills_to_close.append(matching_fill)
                        self.cash += (trade_value - commission)

                    exits_to_remove.append(oid)

        for oid in exits_to_remove:
            del self.pending_exits[oid]
        for f in fills_to_close:
            if f in self.open_fills:
                self.open_fills.remove(f)

        # ============================================================
        # STEP 2b: Process STOP LOSS (closes ALL open fills at once)
        # ============================================================
        if self.open_fills and self.stoploss_level is not None:
            if l <= self.stoploss_level:
                # SL triggered — determine fill price
                if o <= self.stoploss_level:
                    # Gap down: fill at open - slippage
                    sl_fill_price = o - self.slippage
                else:
                    # Normal: fill at SL level - slippage
                    sl_fill_price = self.stoploss_level - self.slippage

                # Close ALL open fills at sl_fill_price
                for fill in list(self.open_fills):
                    trade_value = sl_fill_price * fill.qty
                    commission = self._apply_commission(trade_value)
                    pnl_gross = (sl_fill_price - fill.fill_price) * fill.qty
                    commission_total = fill.commission + commission

                    trade = TradeRecord(
                        entry_id=fill.entry_id,
                        entry_bar_index=fill.fill_bar_index,
                        entry_price=fill.fill_price,
                        entry_qty=fill.qty,
                        exit_bar_index=bar_index,
                        exit_price=sl_fill_price,
                        pnl_gross=pnl_gross,
                        commission_total=commission_total,
                        pnl_net=pnl_gross - commission_total
                    )
                    self.closed_trades.append(trade)
                    self.realized_pnl += trade.pnl_net
                    self.cash += (trade_value - commission)

                self.open_fills.clear()
                self.pending_entries.clear()
                self.pending_exits.clear()
                self.stoploss_level = None
                self.sl_exits += 1

        # ============================================================
        # STEP 3: Update equity
        # ============================================================
        self.equity = self._compute_equity(c)
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity
        dd = self.peak_equity - self.equity
        if dd > self.max_drawdown:
            self.max_drawdown = dd

        self.equity_curve.append((bar.timestamp, self.equity))

        # ============================================================
        # STEP 4: Strategy logic
        # ============================================================
        current_opentrades = self.opentrades

        # --- Detect true bullish reversal bar ---
        self.is_true_bullish_reversal_bar = indicators.is_true_bullish_reversal(
            bar, self.config.enable_ao, self.config.enable_mfi
        )

        # --- Set confirmation/invalidation levels ---
        if self.is_true_bullish_reversal_bar:
            self.bull_bar_confirmation_level = h
            self.bull_bar_invalidation_level = l

        # --- Crossover/crossunder detection ---
        is_bull_bar_invalidated = False
        if (self.prev_low is not None and self.prev_invalid is not None
                and self.bull_bar_invalidation_level is not None):
            if self.prev_low >= self.prev_invalid and l < self.bull_bar_invalidation_level:
                is_bull_bar_invalidated = True

        is_confirmed = False
        if (self.prev_high is not None and self.prev_confirm is not None
                and self.bull_bar_confirmation_level is not None):
            if self.prev_high <= self.prev_confirm and h > self.bull_bar_confirmation_level:
                is_confirmed = True

        if is_confirmed or is_bull_bar_invalidated:
            self.bull_bar_confirmation_level = None
            self.bull_bar_invalidation_level = None

        # --- Layer transitions ---
        if current_opentrades == 1 and self.prev_opentrades == 0:
            self.layer1 = self.position_avg_price
            self.current_layer = 1

        if current_opentrades == 2 and self.prev_opentrades == 1:
            self.current_layer = 2

        if current_opentrades == 3 and self.prev_opentrades == 2:
            self.current_layer = 3

        if current_opentrades == 4 and self.prev_opentrades == 3:
            self.current_layer = 4

        # --- Layer thresholds ---
        if self.layer1 is not None:
            self.layer2_threshold = self.layer1 * (100 - self.config.layer2_threshold_pct) / 100
            self.layer3_threshold = self.layer1 * (100 - self.config.layer3_threshold_pct) / 100
            self.layer4_threshold = self.layer1 * (100 - self.config.layer4_threshold_pct) / 100

        # --- Take profit and stop loss levels ---
        if current_opentrades > 0 and indicators.atr_value is not None:
            self.take_profit_level = (
                self.position_avg_price + indicators.atr_value * self.takeprofit_atr_mult
            )
            self.stoploss_level = (
                self.position_avg_price - indicators.atr_value * self.stoploss_atr_mult
            )
        else:
            self.take_profit_level = None
            self.stoploss_level = None

        # ============================================================
        # STEP 5: Place entry orders (if signal AND conditions AND risk OK)
        # ============================================================
        if in_trading_window and risk_can_enter and self.is_true_bullish_reversal_bar:
            confirm = self.bull_bar_confirmation_level

            if confirm is not None:
                if self.current_layer == 0:
                    qty = self._get_layer_equity_qty(
                        self.config.position_size_multiplier, 0, confirm
                    )
                    self.pending_entries['entry1'] = PendingOrder(
                        order_id='entry1', direction='long',
                        order_type='stop', price=confirm, qty=qty
                    )

                elif self.current_layer == 1 and self.layer2_threshold is not None:
                    if l < self.layer2_threshold:
                        qty = self._get_layer_equity_qty(
                            self.config.position_size_multiplier, 1, confirm
                        )
                        self.pending_entries['entry2'] = PendingOrder(
                            order_id='entry2', direction='long',
                            order_type='stop', price=confirm, qty=qty
                        )

                elif self.current_layer == 2 and self.layer3_threshold is not None:
                    if l < self.layer3_threshold:
                        qty = self._get_layer_equity_qty(
                            self.config.position_size_multiplier, 2, confirm
                        )
                        self.pending_entries['entry3'] = PendingOrder(
                            order_id='entry3', direction='long',
                            order_type='stop', price=confirm, qty=qty
                        )

                elif self.current_layer == 3 and self.layer4_threshold is not None:
                    if l < self.layer4_threshold:
                        qty = self._get_layer_equity_qty(
                            self.config.position_size_multiplier, 3, confirm
                        )
                        self.pending_entries['entry4'] = PendingOrder(
                            order_id='entry4', direction='long',
                            order_type='stop', price=confirm, qty=qty
                        )

        # ============================================================
        # STEP 6: Place/update exit orders for all open fills
        # ============================================================
        if self.take_profit_level is not None:
            for fill in self.open_fills:
                exit_id = f"exit_{fill.entry_id}"
                self.pending_exits[exit_id] = PendingOrder(
                    order_id=exit_id, direction='long',
                    order_type='limit', price=self.take_profit_level,
                    qty=fill.qty, from_entry=fill.entry_id
                )

        # ============================================================
        # STEP 7: Reset layer if no open trades
        # ============================================================
        if self.opentrades == 0:
            self.current_layer = 0

        # ============================================================
        # STEP 8: Save state for next bar
        # ============================================================
        self.prev_high = h
        self.prev_low = l
        self.prev_confirm = self.bull_bar_confirmation_level
        self.prev_invalid = self.bull_bar_invalidation_level
        self.prev_opentrades = self.opentrades

    def force_close_all(self, bar_index: int, price: float):
        """Force close all open positions at given price (end of backtest)."""
        for fill in list(self.open_fills):
            trade_value = price * fill.qty
            commission = self._apply_commission(trade_value)
            pnl_gross = (price - fill.fill_price) * fill.qty
            commission_total = fill.commission + commission

            trade = TradeRecord(
                entry_id=fill.entry_id,
                entry_bar_index=fill.fill_bar_index,
                entry_price=fill.fill_price,
                entry_qty=fill.qty,
                exit_bar_index=bar_index,
                exit_price=price,
                pnl_gross=pnl_gross,
                commission_total=commission_total,
                pnl_net=pnl_gross - commission_total
            )
            self.closed_trades.append(trade)
            self.realized_pnl += trade.pnl_net
            self.cash += (trade_value - commission)

        self.open_fills.clear()
        self.pending_entries.clear()
        self.pending_exits.clear()
