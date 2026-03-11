"""
Adapter for the Candlestick Pro strategy (bitcoin4H account).

Wraps the local `strategies/candlestick-pro` module.

Trades BTC/USD on 4H timeframe using Alpaca's crypto API.
Crypto trades 24/7 — no market hours check needed.

1. Fetch 1H crypto bars from Alpaca, aggregate to 4H
2. Run CandlestickStrategy.analyze() for signal generation
3. Execute signals via the manager's PaperBroker (fractional BTC qty)
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame

from ..base import BaseStrategy, StrategyContext, StrategyEvent

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[5]
CSTICK_REPO = str(REPO_ROOT / "strategies" / "candlestick-pro")

# Bitcoin only, on 4H timeframe (fetched as 1H, aggregated 4x)
SYMBOL = "BTC/USD"
TIMEFRAME_MINUTES = 60  # Fetch 1H bars, aggregate to 4H
AGGREGATION_PERIOD = 4
MIN_RR = 2.0
MIN_CONFIDENCE = 0.55


def _import_candlestick_modules():
    """
    Import CandlestickStrategy from the repo using sys.modules swap.

    The candlestick_pro repo uses 'from src.models import ...' internally,
    which collides with our own 'src' package. We temporarily swap out our
    src modules, let candlestick_pro's imports resolve to its own src/,
    then restore ours.
    """
    saved_modules = {}
    for key in list(sys.modules.keys()):
        if key == "src" or key.startswith("src."):
            saved_modules[key] = sys.modules.pop(key)

    if CSTICK_REPO not in sys.path:
        sys.path.insert(0, CSTICK_REPO)

    try:
        from src.models import PatternType, TimeFrameStyle, Candle
        from src.strategy import CandlestickStrategy
    finally:
        for key in list(sys.modules.keys()):
            if key == "src" or key.startswith("src."):
                del sys.modules[key]
        sys.modules.update(saved_modules)
        if CSTICK_REPO in sys.path:
            sys.path.remove(CSTICK_REPO)

    return CandlestickStrategy, PatternType, TimeFrameStyle, Candle


def _aggregate_candles(candles, period: int):
    """Aggregate smaller candles into larger ones (e.g., 1H -> 4H)."""
    if not candles or period <= 1:
        return candles

    aggregated = []
    for i in range(0, len(candles) - period + 1, period):
        group = candles[i : i + period]
        agg = type(group[0])(
            timestamp=group[0].timestamp,
            open=group[0].open,
            high=max(c.high for c in group),
            low=min(c.low for c in group),
            close=group[-1].close,
            volume=sum(c.volume for c in group if c.volume) or None,
        )
        aggregated.append(agg)

    return aggregated


class CandlestickAdapter(BaseStrategy):
    """
    Live trading adapter for CandlestickStrategy on BTC/USD 4H.

    - Fetches 1H crypto bars from Alpaca, aggregates to 4H
    - Runs engulfing pattern analysis
    - Executes trades with fractional BTC qty via PaperBroker
    - No market hours check (crypto is 24/7)
    """

    def __init__(self):
        self.strategy = None
        self.Candle = None
        self.broker = None
        self.symbol = SYMBOL
        self.scan_count = 0
        self.last_signal_time: Optional[datetime] = None
        self.active_position: Optional[dict] = None

    async def start(self, ctx: StrategyContext) -> None:
        log.info("[bitcoin4H] Starting Candlestick adapter...")

        self.broker = ctx.broker

        CandlestickStrategy, PatternType, TimeFrameStyle, Candle = (
            await asyncio.get_event_loop().run_in_executor(
                None, _import_candlestick_modules
            )
        )

        self.Candle = Candle
        self.strategy = CandlestickStrategy(
            pattern_type=PatternType.ENGULFING,
            style=TimeFrameStyle.SWING,
            min_rr_ratio=MIN_RR,
            min_confidence=MIN_CONFIDENCE,
        )

        log.info(
            "[bitcoin4H] CandlestickStrategy initialized — trading %s on 4H",
            self.symbol,
        )

    async def on_timer(self, ctx: StrategyContext) -> List[StrategyEvent]:
        if not self.strategy:
            return []

        events = []
        self.scan_count += 1
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            # No market hours check — crypto trades 24/7

            # Manage existing position (check for exit conditions)
            await self._manage_position(ctx, events)

            # Scan for new signal
            if not self.active_position:
                try:
                    signal_events = await self._scan(ctx)
                    events.extend(signal_events)
                except Exception as e:
                    log.warning("[bitcoin4H] Error scanning %s: %s", self.symbol, e, exc_info=True)

            if self.scan_count % 3 == 0:
                pos_status = "LONG" if self.active_position else "FLAT"
                events.append(StrategyEvent(
                    timestamp=now, account="bitcoin4H",
                    event_type="info",
                    message=f"Scan #{self.scan_count} complete, {self.symbol} {pos_status}",
                ))

        except Exception as e:
            log.error("[bitcoin4H] Error in on_timer: %s", e, exc_info=True)
            events.append(StrategyEvent(
                timestamp=now, account="bitcoin4H",
                event_type="error", message=f"Error: {e}",
            ))

        return events

    async def _scan(self, ctx: StrategyContext) -> List[StrategyEvent]:
        """Fetch 4H data and run pattern analysis on BTC/USD."""
        events = []
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Rate limit: don't signal within 4 hours of last signal
        if self.last_signal_time:
            elapsed = (datetime.now() - self.last_signal_time).total_seconds()
            if elapsed < 14400:
                return events

        # Fetch 1H crypto bars from Alpaca (using broker's retry wrapper)
        def _fetch_hourly():
            # Use broker.get_crypto_bars() which has _retry wrapper for transient failures
            return self.broker.get_crypto_bars(
                symbol=self.symbol,
                timeframe_minutes=60,
                start=datetime.now(timezone.utc) - timedelta(days=90),
                limit=2000,
            )

        bars = await asyncio.get_event_loop().run_in_executor(
            None, _fetch_hourly,
        )

        if not bars or len(bars) < 60:
            return events

        # Convert to Candle objects
        hourly_candles = []
        for bar in bars:
            try:
                ts = int(bar.timestamp.timestamp() * 1000)
                hourly_candles.append(self.Candle(
                    timestamp=ts,
                    open=float(bar.open),
                    high=float(bar.high),
                    low=float(bar.low),
                    close=float(bar.close),
                    volume=float(bar.volume) if bar.volume else None,
                ))
            except (ValueError, AttributeError):
                continue

        # Aggregate 1H -> 4H
        candles = _aggregate_candles(hourly_candles, AGGREGATION_PERIOD)

        if len(candles) < 60:
            return events

        # Run analysis
        timeframe_data = {"4h": candles}
        idea = await asyncio.get_event_loop().run_in_executor(
            None, self.strategy.analyze, timeframe_data, self.symbol
        )

        if idea and idea.rr_ratio >= MIN_RR:
            self.last_signal_time = datetime.now()

            events.append(StrategyEvent(
                timestamp=now, account="bitcoin4H",
                event_type="signal",
                message=(
                    f"{idea.pattern.value.upper()} {idea.direction.value.upper()} "
                    f"on {self.symbol} — R:R 1:{idea.rr_ratio:.1f} "
                    f"Confidence: {idea.confidence_level}"
                ),
                details={
                    "symbol": self.symbol,
                    "pattern": idea.pattern.value,
                    "direction": idea.direction.value,
                    "entry": idea.entry_price,
                    "stop_loss": idea.stop_loss_price,
                    "take_profit": idea.take_profit_prices[0] if idea.take_profit_prices else 0,
                    "rr_ratio": idea.rr_ratio,
                },
            ))

            order_events = await self._execute_signal(ctx, idea)
            events.extend(order_events)

        return events

    async def _execute_signal(self, ctx: StrategyContext, idea) -> List[StrategyEvent]:
        """Execute a trading signal with fractional BTC sizing."""
        events = []
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            equity = await asyncio.get_event_loop().run_in_executor(
                None, self.broker.get_equity
            )

            # Risk 1% of equity per trade
            risk_amount = equity * 0.01
            risk_per_unit = abs(idea.entry_price - idea.stop_loss_price)
            if risk_per_unit <= 0:
                return events

            # Fractional BTC qty (e.g., 0.0005 BTC)
            qty = risk_amount / risk_per_unit

            # Cap position size at $2500 (manager risk limit)
            max_qty = 2500.0 / idea.entry_price
            qty = min(qty, max_qty)

            # Round to 8 decimal places (BTC precision)
            qty = round(qty, 8)
            if qty <= 0:
                return events

            side = "buy" if idea.direction.value == "long" else "sell"
            exit_side = "sell" if side == "buy" else "buy"
            take_profit = idea.take_profit_prices[0] if idea.take_profit_prices else 0
            stop_loss = idea.stop_loss_price

            order = await asyncio.get_event_loop().run_in_executor(
                None, self.broker.submit_market_order,
                self.symbol, qty, side, "gtc"
            )

            # Submit real Alpaca exit orders so SL/TP survive a process restart.
            # Both are GTC so they persist until filled or manually cancelled.
            sl_order_id = None
            tp_order_id = None

            if stop_loss > 0:
                try:
                    sl_order = await asyncio.get_event_loop().run_in_executor(
                        None, self.broker.submit_stop_order,
                        self.symbol, qty, exit_side, stop_loss, "gtc"
                    )
                    sl_order_id = str(sl_order.id) if sl_order else None
                    log.info("[bitcoin4H] SL order placed: %s @ $%.2f", sl_order_id, stop_loss)
                except Exception as e:
                    log.warning("[bitcoin4H] Failed to place SL order: %s", e)

            if take_profit > 0:
                try:
                    tp_order = await asyncio.get_event_loop().run_in_executor(
                        None, self.broker.submit_limit_order,
                        self.symbol, qty, exit_side, take_profit, "gtc"
                    )
                    tp_order_id = str(tp_order.id) if tp_order else None
                    log.info("[bitcoin4H] TP order placed: %s @ $%.2f", tp_order_id, take_profit)
                except Exception as e:
                    log.warning("[bitcoin4H] Failed to place TP order: %s", e)

            self.active_position = {
                "entry_price": idea.entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "direction": idea.direction.value,
                "qty": qty,
                "entry_time": datetime.now(),
                "sl_order_id": sl_order_id,
                "tp_order_id": tp_order_id,
            }

            events.append(StrategyEvent(
                timestamp=now, account="bitcoin4H",
                event_type="order",
                message=(
                    f"{side.upper()} {qty:.6f} {self.symbol} @ market | "
                    f"SL ${stop_loss:.0f} TP ${take_profit:.0f}"
                ),
                details={"qty": qty, "side": side, "sl": stop_loss, "tp": take_profit},
            ))

        except Exception as e:
            log.error("[bitcoin4H] Order execution failed: %s", e)
            events.append(StrategyEvent(
                timestamp=now, account="bitcoin4H",
                event_type="error",
                message=f"Order failed for {self.symbol}: {e}",
            ))

        return events

    async def _manage_position(self, ctx: StrategyContext, events: list):
        """Check SL/TP for the active BTC position."""
        if not self.active_position:
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            latest = await asyncio.get_event_loop().run_in_executor(
                None, self.broker.get_latest_crypto_bar, self.symbol
            )
            if not latest:
                return

            price = float(latest.close)
            pos = self.active_position
            is_long = pos["direction"] == "long"
            reason = None

            # Check stop loss
            if is_long and price <= pos["stop_loss"]:
                reason = "Stop Loss"
            elif not is_long and price >= pos["stop_loss"]:
                reason = "Stop Loss"

            # Check take profit
            if is_long and price >= pos["take_profit"] > 0:
                reason = "Take Profit"
            elif not is_long and price <= pos["take_profit"] > 0:
                reason = "Take Profit"

            if reason:
                # Cancel the still-open exit order (the one that didn't trigger).
                # e.g. if Stop Loss hit, cancel the pending TP limit order, and vice versa.
                cancel_order_id = None
                if reason == "Stop Loss":
                    cancel_order_id = pos.get("tp_order_id")
                elif reason == "Take Profit":
                    cancel_order_id = pos.get("sl_order_id")

                if cancel_order_id:
                    try:
                        await asyncio.get_event_loop().run_in_executor(
                            None, self.broker.cancel_order, cancel_order_id
                        )
                    except Exception as ce:
                        log.warning("[bitcoin4H] Could not cancel exit order %s: %s", cancel_order_id, ce)

                # Close via Alpaca — use BTCUSD format for position lookup
                close_symbol = self.symbol.replace("/", "")
                await asyncio.get_event_loop().run_in_executor(
                    None, self.broker.close_position, close_symbol
                )
                pnl = (price - pos["entry_price"]) * pos["qty"]
                if not is_long:
                    pnl = -pnl
                events.append(StrategyEvent(
                    timestamp=now, account="bitcoin4H",
                    event_type="fill",
                    message=f"Closed {self.symbol} — {reason} (PnL ~${pnl:.2f})",
                ))
                self.active_position = None

        except Exception as e:
            log.warning("[bitcoin4H] Error checking position: %s", e)

    async def stop(self, ctx: StrategyContext) -> None:
        log.info("[bitcoin4H] Stopping Candlestick adapter...")

    def get_status(self, ctx: StrategyContext) -> Dict[str, Any]:
        if not self.broker:
            return {"equity": ctx.initial_capital, "cash": ctx.initial_capital,
                    "positions": [], "error": "not_initialized"}

        try:
            acct = self.broker.get_account()
            all_positions = self.broker.list_positions()

            pos_list = []
            unrealized = 0.0
            for p in all_positions:
                upl = float(p.unrealized_pl)
                unrealized += upl
                pos_list.append({
                    "symbol": p.symbol,
                    "qty": float(p.qty),
                    "market_value": float(p.market_value),
                    "unrealized_pl": upl,
                    "avg_entry": float(p.avg_entry_price),
                })

            return {
                "equity": float(acct.equity),
                "cash": float(acct.cash),
                "positions": pos_list,
                "position_count": len(all_positions),
                "unrealized_pnl": unrealized,
                "has_position": self.active_position is not None,
                "scan_count": self.scan_count,
                "symbols_watched": 1,
            }
        except Exception as e:
            log.error("[bitcoin4H] Error getting status: %s", e)
            return {"equity": 0, "cash": 0, "positions": [], "error": str(e)}
