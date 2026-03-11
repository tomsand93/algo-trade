"""
Adapter for the TradingView (BDB DCA) Stock Live Bot.

Wraps the local `tradingView` bundle when it is present
without rewriting its trading logic.

The original StockLiveBot uses alpaca-py with env vars ALPACA_API_KEY
and ALPACA_API_SECRET. This adapter:
1. Temporarily sets those env vars to the tradingView account's keys
2. Creates the StockLiveBot
3. Runs warmup once in start()
4. Calls _tick() on each on_timer() instead of the blocking _main_loop()
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

from ..base import BaseStrategy, StrategyContext, StrategyEvent

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[5]
TV_REPO = str(REPO_ROOT / "tradingView")

# High-volume symbols across sectors for DCA strategy diversification.
# Each gets its own StockLiveBot with independent indicators and state.
# Capital is split evenly ($500/symbol at $5k total).
SYMBOLS = [
    "AAPL",   # Tech / Hardware
    "NVDA",   # Semiconductors
    "AMD",    # Semiconductors
    "TSLA",   # EV / Auto
    "MSFT",   # Tech / Software
    "META",   # Tech / Social
    "AMZN",   # E-commerce / Cloud
    "GOOGL",  # Tech / Search
    "JPM",    # Financials
    "XOM",    # Energy
]


def _create_bot(api_key: str, api_secret: str, symbol: str, capital: float):
    """
    Import tradingView modules and create a StockLiveBot instance.

    We temporarily set env vars so AlpacaBroker picks them up,
    then restore the originals.
    """
    if TV_REPO not in sys.path:
        sys.path.insert(0, TV_REPO)

    # Save and replace env vars
    orig_key = os.environ.get("ALPACA_API_KEY")
    orig_secret = os.environ.get("ALPACA_API_SECRET")
    os.environ["ALPACA_API_KEY"] = api_key
    os.environ["ALPACA_API_SECRET"] = api_secret

    try:
        from bdb_dca.config import StrategyConfig
        from bdb_dca.stock_live_bot import StockLiveBot

        config = StrategyConfig(
            symbol=symbol,
            commission_pct=0.0,
            slippage_ticks=0,
            tick_size=0.01,
            initial_capital=capital,
        )

        bot = StockLiveBot(
            config=config,
            risk_config=None,
            dry_run=False,
            paper=True,
        )
        return bot
    finally:
        # Restore original env vars
        if orig_key is not None:
            os.environ["ALPACA_API_KEY"] = orig_key
        elif "ALPACA_API_KEY" in os.environ:
            del os.environ["ALPACA_API_KEY"]
        if orig_secret is not None:
            os.environ["ALPACA_API_SECRET"] = orig_secret
        elif "ALPACA_API_SECRET" in os.environ:
            del os.environ["ALPACA_API_SECRET"]


class TradingViewAdapter(BaseStrategy):
    """Multi-symbol adapter wrapping multiple BDB DCA StockLiveBot instances."""

    def __init__(self):
        self.bots: Dict[str, Any] = {}  # symbol -> StockLiveBot
        self.tick_count = 0
        self._api_key = ""
        self._api_secret = ""
        self._patched = False  # Track if module-level patches are applied

    async def start(self, ctx: StrategyContext) -> None:
        log.info("[tradingView] Starting TradingView adapter...")

        self._api_key = ctx.config.get("api_key", "")
        self._api_secret = ctx.config.get("api_secret", "")

        # Use symbols from config if provided, otherwise use SYMBOLS list
        symbols = ctx.config.get("symbols", SYMBOLS)

        # Split capital evenly across symbols
        capital_per_symbol = ctx.initial_capital / len(symbols)

        for symbol in symbols:
            try:
                bot = await asyncio.get_event_loop().run_in_executor(
                    None,
                    _create_bot,
                    self._api_key,
                    self._api_secret,
                    symbol,
                    capital_per_symbol,
                )
                await self._startup_bot(ctx, bot, symbol)
                self.bots[symbol] = bot
                log.info("[tradingView] Bot initialized and warmed up for %s", symbol)
            except Exception as e:
                log.error("[tradingView] Failed to initialize bot for %s: %s", symbol, e, exc_info=True)

        if not self.bots:
            raise RuntimeError("No bots initialized successfully")

        log.info("[tradingView] %d/%d bots ready. Live data source: Alpaca", len(self.bots), len(symbols))

    async def _startup_bot(self, ctx: StrategyContext, bot, symbol: str) -> None:
        """Initialize a single bot: connect broker, warmup, apply patches."""

        def _startup():
            orig_key = os.environ.get("ALPACA_API_KEY")
            orig_secret = os.environ.get("ALPACA_API_SECRET")
            os.environ["ALPACA_API_KEY"] = self._api_key
            os.environ["ALPACA_API_SECRET"] = self._api_secret
            try:
                intended_capital = bot.config.initial_capital
                bot._connect_broker()
                # _connect_broker() overrides initial_capital with the full Alpaca
                # account equity (~$5000). Restore it to the per-symbol allocation
                # ($500) so position sizing stays proportional to each bot's slice.
                bot.config.initial_capital = intended_capital
                bot.trade_logger = bot.__class__.__mro__[0].__init__  # avoid re-init
                from bdb_dca.stock_live_bot import StockTradeLogger
                bot.trade_logger = StockTradeLogger(bot.symbol)
                from bdb_dca.indicators import IndicatorState
                bot.indicators = IndicatorState(
                    jaw_length=bot.config.jaw_length,
                    jaw_offset=bot.config.jaw_offset,
                    teeth_length=bot.config.teeth_length,
                    teeth_offset=bot.config.teeth_offset,
                    lips_length=bot.config.lips_length,
                    lips_offset=bot.config.lips_offset,
                    atr_length=bot.config.atr_length,
                    lowest_bars=bot.config.lowest_bars,
                )
                from bdb_dca.strategy import StrategyState
                bot.strategy = StrategyState(bot.config)
                from bdb_dca.order_manager import OrderManager
                bot.order_manager = OrderManager(
                    broker=bot.broker,
                    strategy=bot.strategy,
                    symbol=bot.symbol,
                    session_id=bot.session_id,
                )

                # Apply module-level patches only once (shared across all bots)
                if not self._patched:
                    self._apply_patches(ctx)
                    self._patched = True

                bot._warmup()
                bot.running = True
            finally:
                if orig_key is not None:
                    os.environ["ALPACA_API_KEY"] = orig_key
                elif "ALPACA_API_KEY" in os.environ:
                    del os.environ["ALPACA_API_KEY"]
                if orig_secret is not None:
                    os.environ["ALPACA_API_SECRET"] = orig_secret
                elif "ALPACA_API_SECRET" in os.environ:
                    del os.environ["ALPACA_API_SECRET"]

        await asyncio.get_event_loop().run_in_executor(None, _startup)

        # Monkey-patch broker's position lookups to avoid 3x retry on 404
        broker = bot.broker
        client = broker.client

        def _get_stock_position_no_retry(sym):
            try:
                return client.get_open_position(sym)
            except Exception:
                return None

        def _get_crypto_position_no_retry():
            try:
                return client.get_open_position("BTC/USD")
            except Exception:
                return None

        broker.get_stock_position = _get_stock_position_no_retry
        broker.get_crypto_position = _get_crypto_position_no_retry

    def _apply_patches(self, ctx: StrategyContext) -> None:
        """Apply module-level patches for data sourcing (once for all bots)."""
        import bdb_dca.stock_live_data as sld
        from bdb_dca.models import Bar as TVBar

        alpaca_broker = ctx.broker
        _orig_warmup = sld.fetch_stock_warmup_bars

        def _warmup_via_alpaca(symbol, days=90):
            period_days = min(days, 59)
            log.info("[tradingView] Fetching %d days of warmup bars for %s via Alpaca",
                     period_days, symbol)
            try:
                start = datetime.now(timezone.utc) - timedelta(days=period_days)
                alpaca_bars = alpaca_broker.get_bars(
                    symbol, 30, start=start, limit=5000
                )
                log.info("[tradingView] Alpaca returned %d raw bars", len(alpaca_bars))

                bars = []
                for b in alpaca_bars:
                    ts_ms = int(b.timestamp.timestamp() * 1000)
                    bar = TVBar(
                        timestamp=ts_ms,
                        open=float(b.open),
                        high=float(b.high),
                        low=float(b.low),
                        close=float(b.close),
                        volume=float(b.volume) if b.volume else 0.0,
                    )
                    if sld._is_market_hours_bar(bar.timestamp):
                        bars.append(bar)

                bars.sort(key=lambda b: b.timestamp)
                log.info("[tradingView] Fetched %d warmup bars via Alpaca (after market hours filter)", len(bars))
                if bars:
                    return bars
                log.warning("[tradingView] Alpaca returned 0 bars, falling back to yfinance")
                return _orig_warmup(symbol, days)
            except Exception as e:
                log.warning("[tradingView] Alpaca warmup failed (%s), falling back to yfinance", e)
                return _orig_warmup(symbol, days)

        sld.fetch_stock_warmup_bars = _warmup_via_alpaca
        import bdb_dca.stock_live_bot as slb
        slb.fetch_stock_warmup_bars = _warmup_via_alpaca

        def _fetch_bars_via_alpaca(symbol, count=10):
            try:
                # Fetch more than needed so we can slice the MOST RECENT `count` bars.
                # Alpaca returns bars in chronological order from `start`, so limit=count
                # would give the OLDEST bars in the window, not the newest.
                bars = alpaca_broker.get_bars(symbol, 30, limit=max(count * 20, 200))
                result = []
                for b in bars:
                    ts_ms = int(b.timestamp.timestamp() * 1000)
                    result.append(TVBar(
                        timestamp=ts_ms,
                        open=float(b.open),
                        high=float(b.high),
                        low=float(b.low),
                        close=float(b.close),
                        volume=float(b.volume) if b.volume else 0.0,
                    ))
                # Return only the most recent `count` bars
                return result[-count:] if len(result) > count else result
            except Exception as e:
                log.warning("[tradingView] Alpaca bar fetch failed: %s", e)
                return []

        sld.fetch_latest_stock_bars = _fetch_bars_via_alpaca

    async def on_timer(self, ctx: StrategyContext) -> List[StrategyEvent]:
        if not self.bots:
            return []

        events = []
        self.tick_count += 1
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            orig_key = os.environ.get("ALPACA_API_KEY")
            orig_secret = os.environ.get("ALPACA_API_SECRET")
            os.environ["ALPACA_API_KEY"] = self._api_key
            os.environ["ALPACA_API_SECRET"] = self._api_secret

            try:
                for symbol, bot in self.bots.items():
                    if not bot.running:
                        continue
                    try:
                        prev_trades = len(bot.strategy.closed_trades) if bot.strategy else 0

                        await asyncio.get_event_loop().run_in_executor(
                            None, bot._tick
                        )

                        if bot.strategy:
                            new_trades = bot.strategy.closed_trades[prev_trades:]
                            for trade in new_trades:
                                events.append(StrategyEvent(
                                    timestamp=now, account="tradingView",
                                    event_type="fill",
                                    message=(
                                        f"[{symbol}] Trade closed: {trade.entry_id} "
                                        f"PnL=${trade.pnl_net:.2f}"
                                    ),
                                    details={
                                        "symbol": symbol,
                                        "entry_price": trade.entry_price,
                                        "exit_price": trade.exit_price,
                                        "pnl": trade.pnl_net,
                                    },
                                ))
                    except Exception as e:
                        log.warning("[tradingView] Error ticking %s: %s", symbol, e)

                if self.tick_count % 3 == 0:
                    active = [s for s, b in self.bots.items() if b.running]
                    events.append(StrategyEvent(
                        timestamp=now, account="tradingView",
                        event_type="info",
                        message=f"Tick #{self.tick_count} completed ({len(active)} symbols active)",
                    ))

            finally:
                if orig_key is not None:
                    os.environ["ALPACA_API_KEY"] = orig_key
                elif "ALPACA_API_KEY" in os.environ:
                    del os.environ["ALPACA_API_KEY"]
                if orig_secret is not None:
                    os.environ["ALPACA_API_SECRET"] = orig_secret
                elif "ALPACA_API_SECRET" in os.environ:
                    del os.environ["ALPACA_API_SECRET"]

        except Exception as e:
            log.error("[tradingView] Error in on_timer: %s", e, exc_info=True)
            events.append(StrategyEvent(
                timestamp=now, account="tradingView",
                event_type="error", message=f"Error: {e}",
            ))

        return events

    async def stop(self, ctx: StrategyContext) -> None:
        log.info("[tradingView] Stopping TradingView adapter (%d bots)...", len(self.bots))
        for symbol, bot in self.bots.items():
            bot.running = False
            try:
                if bot.order_manager:
                    await asyncio.get_event_loop().run_in_executor(
                        None, bot.order_manager.cancel_all_entries
                    )
                if bot.strategy:
                    await asyncio.get_event_loop().run_in_executor(
                        None, bot._save_state
                    )
            except Exception as e:
                log.error("[tradingView] Error stopping %s: %s", symbol, e)

    def get_status(self, ctx: StrategyContext) -> Dict[str, Any]:
        if not self.bots:
            return {"equity": ctx.initial_capital, "cash": ctx.initial_capital,
                    "positions": [], "error": "not_initialized"}

        try:
            positions = []
            total_realized = 0.0
            total_open_fills = 0
            total_closed_trades = 0

            orig_key = os.environ.get("ALPACA_API_KEY")
            orig_secret = os.environ.get("ALPACA_API_SECRET")
            os.environ["ALPACA_API_KEY"] = self._api_key
            os.environ["ALPACA_API_SECRET"] = self._api_secret

            try:
                # Use the first bot's broker for account-level data (same account)
                first_bot = next(iter(self.bots.values()))
                acct = first_bot.broker.get_account()
                equity = float(acct.equity)
                cash = float(acct.cash)

                for symbol, bot in self.bots.items():
                    # Get position for each symbol
                    pos = bot.broker.get_stock_position(symbol)
                    if pos:
                        positions.append({
                            "symbol": symbol,
                            "qty": float(pos.qty),
                            "market_value": float(pos.market_value),
                            "unrealized_pl": float(pos.unrealized_pl),
                            "avg_entry": float(pos.avg_entry_price),
                        })

                    if bot.strategy:
                        total_realized += bot.strategy.realized_pnl
                        total_open_fills += len(bot.strategy.open_fills)
                        total_closed_trades += len(bot.strategy.closed_trades)
            finally:
                if orig_key is not None:
                    os.environ["ALPACA_API_KEY"] = orig_key
                elif "ALPACA_API_KEY" in os.environ:
                    del os.environ["ALPACA_API_KEY"]
                if orig_secret is not None:
                    os.environ["ALPACA_API_SECRET"] = orig_secret
                elif "ALPACA_API_SECRET" in os.environ:
                    del os.environ["ALPACA_API_SECRET"]

            return {
                "equity": equity,
                "cash": cash,
                "positions": positions,
                "position_count": len(positions),
                "unrealized_pnl": sum(p["unrealized_pl"] for p in positions),
                "realized_pnl": total_realized,
                "open_fills": total_open_fills,
                "closed_trades": total_closed_trades,
                "symbols_active": len([b for b in self.bots.values() if b.running]),
                "symbols_total": len(self.bots),
                "bar_index": max((b.bar_index for b in self.bots.values()), default=0),
            }
        except Exception as e:
            log.error("[tradingView] Error getting status: %s", e)
            return {"equity": 0, "cash": 0, "positions": [], "error": str(e)}
