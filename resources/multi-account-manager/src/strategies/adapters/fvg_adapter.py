"""
Adapter for the FVG Breakout Strategy.

Wraps the local `strategies/fvg-breakout` module
without rewriting its trading logic.

The original PaperTrader uses alpaca-trade-api (old SDK) and reads config
from alpaca_config.py. This adapter monkey-patches the config at import
time to inject the correct credentials from env vars, then delegates
scan/execute logic to the original PaperTrader class.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from ..base import BaseStrategy, StrategyContext, StrategyEvent

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[5]
FVG_REPO = str(REPO_ROOT / "strategies" / "fvg-breakout")


def _import_fvg_modules(api_key: str, api_secret: str):
    """
    Import the FVG strategy modules with injected credentials.

    The FVG repo uses 'from src.pattern_detection import ...' internally,
    which collides with our own 'src' package. We temporarily swap out our
    src modules, let the FVG repo's imports resolve to its own src/,
    then restore ours.
    """
    # 1. Save and remove our own src.* module entries
    saved_modules = {}
    for key in list(sys.modules.keys()):
        if key == "src" or key.startswith("src."):
            saved_modules[key] = sys.modules.pop(key)

    # 2. Put FVG repo at front of sys.path
    if FVG_REPO not in sys.path:
        sys.path.insert(0, FVG_REPO)

    try:
        # 3. Import and patch config BEFORE importing PaperTrader
        import alpaca_config
        alpaca_config.ALPACA_PAPER_CONFIG = {
            "base_url": "https://paper-api.alpaca.markets",
            "api_key": api_key,
            "api_secret": api_secret,
        }

        # 4. Now 'from src.pattern_detection ...' resolves to fvg_breakout_strategy/src/
        import paper_trader
        paper_trader.ALPACA_PAPER_CONFIG = alpaca_config.ALPACA_PAPER_CONFIG

        PaperTrader = paper_trader.PaperTrader
    finally:
        # 5. Remove FVG's src.* entries from sys.modules
        for key in list(sys.modules.keys()):
            if key == "src" or key.startswith("src."):
                del sys.modules[key]

        # 6. Restore our own src.* entries
        sys.modules.update(saved_modules)

        # 7. Clean up sys.path
        if FVG_REPO in sys.path:
            sys.path.remove(FVG_REPO)

    return PaperTrader


class FVGAdapter(BaseStrategy):
    """Thin adapter wrapping FVG Breakout Strategy's PaperTrader."""

    def __init__(self):
        self.trader = None
        self.scan_count = 0

    async def start(self, ctx: StrategyContext) -> None:
        log.info("[fvg] Starting FVG adapter...")

        PaperTrader = await asyncio.get_event_loop().run_in_executor(
            None,
            _import_fvg_modules,
            ctx.config["api_key"],
            ctx.config["api_secret"],
        )

        # Create the PaperTrader instance (this connects to Alpaca internally)
        self.trader = await asyncio.get_event_loop().run_in_executor(
            None, PaperTrader
        )

        log.info("[fvg] PaperTrader initialized with %d symbols", len(self.trader.symbols))

    async def on_timer(self, ctx: StrategyContext) -> List[StrategyEvent]:
        if not self.trader:
            return []

        events = []
        self.scan_count += 1
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            # Check if market is open
            is_open = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.trader.get_clock()
            )

            if not is_open or not is_open.get("is_open", False):
                if self.scan_count % 10 == 1:  # Only report once every 10 scans
                    return [StrategyEvent(
                        timestamp=now, account="fvg",
                        event_type="info", message="Market closed, waiting..."
                    )]
                return []

            # Check position count
            positions = await asyncio.get_event_loop().run_in_executor(
                None, self.trader.api.list_positions
            )

            if len(positions) >= self.trader.max_positions:
                return [StrategyEvent(
                    timestamp=now, account="fvg",
                    event_type="info",
                    message=f"Max positions reached ({len(positions)}/{self.trader.max_positions})"
                )]

            # Scan for FVG setups
            setups = await asyncio.get_event_loop().run_in_executor(
                None, self.trader.scan_for_setups
            )

            if setups:
                events.append(StrategyEvent(
                    timestamp=now, account="fvg",
                    event_type="signal",
                    message=f"Found {len(setups)} FVG setup(s)",
                ))

                for setup in setups:
                    # Validate bracket order prices before submitting
                    skip_reason = None
                    if setup.stop_loss >= setup.entry_price:
                        skip_reason = f"stop_loss (${setup.stop_loss:.2f}) >= entry (${setup.entry_price:.2f})"
                    elif setup.take_profit <= setup.entry_price:
                        skip_reason = f"take_profit (${setup.take_profit:.2f}) <= entry (${setup.entry_price:.2f})"
                    else:
                        # Also validate against current market price
                        try:
                            latest = await asyncio.get_event_loop().run_in_executor(
                                None, self.trader.api.get_latest_trade, setup.symbol
                            )
                            mkt_price = float(latest.price)
                            if setup.stop_loss >= mkt_price - 0.01:
                                skip_reason = f"stop_loss (${setup.stop_loss:.2f}) >= market price (${mkt_price:.2f})"
                            elif setup.take_profit <= mkt_price + 0.01:
                                skip_reason = f"take_profit (${setup.take_profit:.2f}) <= market price (${mkt_price:.2f})"
                        except Exception:
                            pass  # proceed if price check fails

                    if skip_reason:
                        log.warning("[fvg] Skipping %s: %s", setup.symbol, skip_reason)
                        events.append(StrategyEvent(
                            timestamp=now, account="fvg",
                            event_type="info",
                            message=f"Skipped {setup.symbol}: {skip_reason}",
                        ))
                        continue

                    # Execute trade via the original logic
                    order = await asyncio.get_event_loop().run_in_executor(
                        None, self.trader.execute_trade, setup
                    )
                    if order:
                        events.append(StrategyEvent(
                            timestamp=now, account="fvg",
                            event_type="order",
                            message=f"BUY {setup.symbol} @ ${setup.entry_price:.2f}",
                            details={
                                "symbol": setup.symbol,
                                "entry": setup.entry_price,
                                "stop_loss": setup.stop_loss,
                                "take_profit": setup.take_profit,
                            },
                        ))
            else:
                if self.scan_count % 5 == 0:  # Log every 5th scan to reduce noise
                    events.append(StrategyEvent(
                        timestamp=now, account="fvg",
                        event_type="info",
                        message=f"Scan #{self.scan_count}: no setups found",
                    ))

        except Exception as e:
            log.error("[fvg] Error in on_timer: %s", e, exc_info=True)
            events.append(StrategyEvent(
                timestamp=now, account="fvg",
                event_type="error", message=f"Error: {e}",
            ))

        return events

    async def stop(self, ctx: StrategyContext) -> None:
        log.info("[fvg] Stopping FVG adapter...")
        # The original PaperTrader doesn't have explicit cleanup beyond
        # letting bracket orders (SL/TP) manage positions.

    def get_status(self, ctx: StrategyContext) -> Dict[str, Any]:
        if not self.trader:
            return {"equity": ctx.initial_capital, "cash": ctx.initial_capital,
                    "positions": [], "trades_today": 0, "error": "not_initialized"}

        try:
            account = self.trader.get_account()
            positions = self.trader.api.list_positions()

            pos_list = []
            unrealized_total = 0.0
            for p in positions:
                upl = float(p.unrealized_pl)
                unrealized_total += upl
                pos_list.append({
                    "symbol": p.symbol,
                    "qty": int(float(p.qty)),
                    "market_value": float(p.market_value),
                    "unrealized_pl": upl,
                    "avg_entry": float(p.avg_entry_price),
                })

            return {
                "equity": account["equity"] if account else 0,
                "cash": account["cash"] if account else 0,
                "buying_power": account.get("buying_power", 0) if account else 0,
                "positions": pos_list,
                "position_count": len(positions),
                "unrealized_pnl": unrealized_total,
                "trades_today": len(self.trader.daily_trades),
                "scan_count": self.scan_count,
            }
        except Exception as e:
            log.error("[fvg] Error getting status: %s", e)
            return {"equity": 0, "cash": 0, "positions": [], "error": str(e)}
