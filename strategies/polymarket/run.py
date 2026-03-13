#!/usr/bin/env python3
"""Polymarket trading bot — Phase 4 entry point.

Usage:
    python run.py --mode mock      # synthetic mock data (5 markets, no file needed)
    python run.py --mode replay    # replay recorded JSONL snapshot
    python run.py --mode backtest --data data/historical/fixture_mean_reversion.csv
    python run.py --mode paper     # live market data, simulated fills (continuous loop)
    python run.py --mode live --i-know-what-im-doing  # real orders (continuous loop)

The bot:
  1. Loads configuration from .env (or defaults)
  2. Sets up structured console logging
  3. Instantiates the appropriate data client
  4. Runs the selected strategy against each market state with full risk controls
  5. Simulates order placement for actionable signals
  6. Logs all events (CONFIG LOADED, RISK CONFIG, SIGNAL, ORDER, RUN COMPLETE)

Phase 4: Paper mode polls live Polymarket API (L0, no auth). Live mode places real orders (L2, full auth).
Graceful shutdown: Ctrl+C triggers save_state() before exit.
Phase 3: Backtest mode added — loads CSV/JSON, runs strategy, prints summary, saves JSON report.
Phase 2: All orders are simulated — no real API calls, no real money.
Call sequence per tick: check_stops → generate_signal → should_trade → risk.check → simulate_order/place_live_order → record_fill.
"""
import argparse
import os
import signal
import sys
import time
from datetime import datetime, timezone

from loguru import logger

from polymarket_bot.config import load_settings
from polymarket_bot.logger import setup_logger
from polymarket_bot.models import SimulatedOrder
from polymarket_bot.risk import RiskManager
from polymarket_bot.strategy import MeanReversionStrategy, MomentumStrategy


# Module-level shutdown flag — set by signal handler, checked by run_paper_or_live()
# Bool assignment is GIL-atomic: safe to set from signal handler.
_shutdown: bool = False


def _handle_signal(signum, frame) -> None:
    """Signal handler: set shutdown flag ONLY. Never block, never raise, never call logger.

    Signal handlers run in the main thread but interrupt the GIL mid-operation.
    Calling logger, json.dump, or acquiring locks here causes deadlock.
    All cleanup (save_state, log flush) happens in the main thread after loop exits.
    """
    global _shutdown
    _shutdown = True


def find_latest_snapshot(snapshot_dir: str) -> str | None:
    """Return path to the most recent .jsonl file in snapshot_dir, or None."""
    if not os.path.isdir(snapshot_dir):
        return None
    candidates = [
        os.path.join(snapshot_dir, f)
        for f in os.listdir(snapshot_dir)
        if f.endswith(".jsonl")
    ]
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def log_config(settings) -> None:
    """Log all active config values at startup. Secrets are never logged."""
    logger.info(
        "CONFIG LOADED | z_entry={z_entry} | z_exit={z_exit} | window={window} | "
        "max_position=${max_pos} | daily_loss_limit=${loss_limit} | "
        "snapshot_dir={snap_dir} | log_level={level}",
        z_entry=settings.z_entry_threshold,
        z_exit=settings.z_exit_threshold,
        window=settings.rolling_window,
        max_pos=settings.max_position_size,
        loss_limit=settings.daily_loss_limit,
        snap_dir=settings.snapshot_dir,
        level=settings.log_level,
    )
    logger.info(
        "RISK CONFIG | stop_loss={sl:.0%} | cooldown={cd}s | initial_capital=${cap}",
        sl=settings.stop_loss_pct,
        cd=settings.cooldown_seconds,
        cap=settings.initial_capital,
    )
    # Explicitly note that API keys are configured (or not) without exposing values
    has_key = bool(settings.polymarket_api_key.get_secret_value())
    logger.info("API credentials: {}", "configured" if has_key else "not set (mock/replay mode)")


def simulate_order(signal, market_state, max_position_size: float = 10.0) -> SimulatedOrder:
    """Create a SimulatedOrder from a signal.

    Phase 2: quantity = max_position_size / fill_price (capital-based sizing).
    Ensures USD exposure never exceeds max_position_size per market.
    """
    side = "YES" if "YES" in signal.direction else "NO"
    direction = "BUY" if "BUY" in signal.direction else "SELL"
    fill_price = signal.price

    # Capital-based quantity: how many tokens can we buy for max_position_size dollars?
    # Guard against zero/near-zero prices to avoid division by zero
    quantity = round(max_position_size / fill_price, 4) if fill_price > 0 else 0.0

    return SimulatedOrder(
        market_id=signal.market_id,
        side=side,
        direction=direction,
        fill_price=fill_price,
        quantity=quantity,
        timestamp=datetime.now(timezone.utc),
    )


def run_loop(client, strategy, risk_manager: RiskManager, live_mode: bool = False) -> int:
    """Run the main strategy loop over all market states from the client.

    Phase 2 call sequence per market tick:
      1. check_stops(market_state)    — exit open positions hitting stop-loss
      2. generate_signal(market_state) — entry candidate from strategy
      3. should_trade(signal, ...)    — confidence pre-filter on strategy
      4. risk_manager.check(...)      — risk gate (position, loss, cooldown)
      5. simulate_order(...)          — paper fill with capital-based qty
      6. record_fill(order, stop)     — update RiskManager position state

    Returns the count of signals generated (including those blocked by risk gate).
    """
    signal_count = 0
    orders: list[SimulatedOrder] = []

    for market_state in client.get_market_states():
        # Step 1: Check stop-loss for any open position in this market
        exit_signal = risk_manager.check_stops(market_state)
        if exit_signal is not None:
            logger.warning(
                "STOP-LOSS EXIT | market={market} | {reason}",
                market=market_state.market_id,
                reason=exit_signal.reason,
            )

        # Step 2: Generate entry signal
        signal = strategy.generate_signal(market_state)
        if signal is None:
            continue

        signal_count += 1
        logger.info(
            "SIGNAL: {direction} @ {price:.2f} | market: '{question}' | "
            "confidence: {confidence:.2f} | reason: {reason}",
            direction=signal.direction,
            price=signal.price,
            question=market_state.question,
            confidence=signal.confidence,
            reason=signal.reason,
        )

        # Step 3: Confidence pre-filter (strategy-level gate)
        if not strategy.should_trade(signal, market_state):
            logger.debug(
                "SIGNAL SKIPPED (low confidence) | {direction} confidence={conf:.2f}",
                direction=signal.direction,
                conf=signal.confidence,
            )
            continue

        # Step 4: Risk gate (RiskManager — position, loss, cooldown, circuit breaker)
        if not risk_manager.check(signal, market_state):
            logger.debug(
                "SIGNAL BLOCKED (risk gate) | {direction} | halted={halted}",
                direction=signal.direction,
                halted=risk_manager.is_halted,
            )
            continue

        # Step 5: Place or simulate order
        if live_mode:
            # Live mode: submit real signed order to CLOB via PolymarketLiveClient.
            # token_id is resolved internally by PolymarketLiveClient from its _token_id_cache
            # (populated during get_market_states() in this same tick). Do NOT pass token_id here.
            order = client.place_live_order(signal, risk_manager.max_position_size)
        else:
            # Paper/mock/replay mode: simulate fill, no real order placed
            order = simulate_order(signal, market_state, risk_manager.max_position_size)
        orders.append(order)
        logger.info(
            "ORDER: {direction} {side} @ {price:.4f} | qty: {qty:.4f} | "
            "order_id: {order_id} | market: '{market_id}'",
            direction=order.direction,
            side=order.side,
            price=order.fill_price,
            qty=order.quantity,
            order_id=order.order_id,
            market_id=order.market_id,
        )

        # Step 6: Update risk manager state
        stop_price = round(order.fill_price * (1.0 - risk_manager.stop_loss_pct), 4)
        risk_manager.record_fill(order, stop_price)

    logger.info(
        "RUN COMPLETE | signals={signals} | orders={orders} | "
        "filled={filled} | cancelled={cancelled} | halted={halted}",
        signals=signal_count,
        orders=len(orders),
        filled=sum(1 for o in orders if o.status == "FILLED"),
        cancelled=sum(1 for o in orders if o.status == "CANCELLED"),
        halted=risk_manager.is_halted,
    )
    return signal_count


def run_backtest(args, settings) -> None:
    """Run backtest mode: load data, execute backtest, print summary, save report."""
    from polymarket_bot.backtester import Backtester, save_report
    from polymarket_bot.data_loader import load_csv, load_json

    # Validate --data argument
    if args.data is None:
        logger.error("--mode backtest requires --data <path/to/file.csv or .json>")
        sys.exit(1)

    if not os.path.exists(args.data):
        logger.error("Data file not found: {}", args.data)
        sys.exit(1)

    # Load data (CSV or JSON based on extension)
    ext = os.path.splitext(args.data)[1].lower()
    if ext == ".json":
        market_states = load_json(args.data)
    else:
        market_states = load_csv(args.data)

    if not market_states:
        logger.error("No valid market states loaded from {}", args.data)
        sys.exit(1)

    logger.info(
        "BACKTEST | loaded {} states from {} | strategy={}",
        len(market_states),
        args.data,
        args.strategy,
    )

    # Instantiate strategy (same pattern as main())
    if args.strategy == "momentum":
        strategy = MomentumStrategy(
            short_window=5,
            long_window=settings.rolling_window,
        )
    else:
        strategy = MeanReversionStrategy(
            window=settings.rolling_window,
            z_entry=settings.z_entry_threshold,
            z_exit=settings.z_exit_threshold,
        )

    # Run backtest
    backtester = Backtester(
        strategy=strategy,
        initial_capital=settings.initial_capital,
        max_position_size=settings.max_position_size,
        daily_loss_limit=settings.daily_loss_limit,
        stop_loss_pct=settings.stop_loss_pct,
        cooldown_seconds=0,      # no cooldown in backtest (historical data, not real-time)
        fee_rate=args.fee_rate,
        slippage_pct=args.slippage,
    )
    report = backtester.run(market_states)

    # Print summary to console
    logger.info(
        "BACKTEST COMPLETE | trades={trades} | win_rate={wr:.1f}% | "
        "return={ret:.2f}% | sharpe={sharpe} | sortino={sortino} | "
        "max_drawdown={dd:.2f}% | initial=${init:.2f} | final=${final:.2f}",
        trades=report.total_trades,
        wr=report.win_rate_pct,
        ret=report.total_return_pct,
        sharpe=f"{report.sharpe_ratio:.3f}" if report.sharpe_ratio is not None else "N/A",
        sortino=f"{report.sortino_ratio:.3f}" if report.sortino_ratio is not None else "N/A",
        dd=report.max_drawdown_pct,
        init=report.initial_capital,
        final=report.final_capital,
    )

    # Save JSON report to data/backtest_results/
    from datetime import datetime as _dt
    timestamp_str = _dt.now().strftime("%Y%m%d_%H%M%S")
    strategy_slug = args.strategy.replace("_", "")
    output_dir = "data/backtest_results"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"backtest_{strategy_slug}_{timestamp_str}.json")
    save_report(report, output_path)


def _run_live_preflight(client, settings) -> None:
    """Run pre-flight checks before enabling live order placement.

    Calls sys.exit(1) on any failure — never starts live mode in a degraded state.
    Checks: (1) API reachable, (2) client is L2, (3) wallet address resolves.
    """
    logger.info("LIVE PRE-FLIGHT: running checks...")

    # 1. Verify API connectivity
    try:
        ok = client._clob.get_ok()
        assert ok is not None
    except Exception as exc:
        logger.critical("PRE-FLIGHT FAIL: Cannot reach Polymarket CLOB: {}", exc)
        sys.exit(1)

    # 2. Verify L2 auth mode
    if client._clob.mode < 2:
        logger.critical(
            "PRE-FLIGHT FAIL: Client is not in L2 mode (mode={}). "
            "Check POLYMARKET_PRIVATE_KEY and API credentials in .env",
            client._clob.mode,
        )
        sys.exit(1)

    # 3. Verify wallet address resolves
    address = client._clob.get_address()
    if not address:
        logger.critical(
            "PRE-FLIGHT FAIL: Could not resolve wallet address from private key. "
            "Verify POLYMARKET_PRIVATE_KEY is set correctly in .env"
        )
        sys.exit(1)

    logger.info("LIVE PRE-FLIGHT PASSED | wallet={}", address)
    logger.warning(
        "LIVE TRADING ENABLED — real orders WILL be placed. "
        "max_position=${} | daily_loss_limit=${}",
        settings.max_position_size,
        settings.daily_loss_limit,
    )


def run_paper_or_live(client, strategy, risk_manager: RiskManager, settings, live: bool) -> None:
    """Continuous polling loop for paper and live modes.

    Loop: while not _shutdown: run_loop() + sleep(poll_interval_seconds)
    Shutdown: set by _handle_signal() on SIGINT/SIGTERM.
    State: load_state() before loop, save_state() after loop exits.
    """
    global _shutdown
    _shutdown = False

    # Register signal handlers — set flag only, cleanup in main thread
    signal.signal(signal.SIGINT, _handle_signal)
    try:
        signal.signal(signal.SIGTERM, _handle_signal)
    except (OSError, ValueError):
        pass  # SIGTERM may not be available on all platforms

    # Local import is intentional: keeps state_manager dependency explicit, avoids circular
    # import risk, and ensures tests can patch polymarket_bot.state_manager.save_state
    # (not run.save_state) — see test_save_state_called_on_shutdown docstring for details.
    from polymarket_bot.state_manager import load_state, save_state
    loaded = load_state(risk_manager, settings.state_file)
    if not loaded:
        logger.info("Starting with fresh position state (no prior state file)")

    poll_interval = settings.poll_interval_seconds
    mode_name = "LIVE" if live else "PAPER"
    logger.info(
        "STARTING {} MODE | poll_interval={}s | strategy={}",
        mode_name,
        poll_interval,
        type(strategy).__name__,
    )

    while not _shutdown:
        try:
            run_loop(client, strategy, risk_manager, live_mode=live)
        except Exception as exc:
            logger.error("Poll tick error (will retry next interval): {}", exc)

        if not _shutdown:
            time.sleep(poll_interval)

    # Main-thread cleanup — safe to call logger and save_state here
    logger.info("SHUTDOWN: saving position state to {}...", settings.state_file)
    save_state(risk_manager, settings.state_file)
    logger.info("SHUTDOWN COMPLETE | {} mode stopped cleanly", mode_name)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Polymarket trading bot — Phase 4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Modes:\n"
            "  mock      — synthetic data (5 markets, no snapshot file required)\n"
            "  replay    — replay real data from most recent JSONL snapshot\n"
            "  backtest  — run strategy against historical CSV/JSON data file\n"
            "  paper     — poll live Polymarket API, simulate fills (no real orders)\n"
            "  live      — place real orders (requires --i-know-what-im-doing flag)\n"
            "\nBacktest example:\n"
            "  python run.py --mode backtest --data data/historical/fixture_mean_reversion.csv\n"
            "\nPaper trading example:\n"
            "  python run.py --mode paper\n"
            "\nCredential setup (run once before live trading):\n"
            "  python scripts/derive_creds.py\n"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["mock", "replay", "backtest", "paper", "live"],
        required=True,
        help="Data source mode",
    )
    parser.add_argument(
        "--strategy",
        choices=["mean_reversion", "momentum"],
        default="mean_reversion",
        help="Strategy to use (default: mean_reversion)",
    )
    parser.add_argument(
        "--data",
        default=None,
        help="Path to historical data CSV/JSON file (required for --mode backtest)",
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=0.005,
        help="Slippage percentage for backtest fills (default: 0.005 = 0.5%%)",
    )
    parser.add_argument(
        "--fee-rate",
        type=float,
        default=0.0,
        help="Fee rate as fraction of fill value (default: 0.0 = fee-free)",
    )
    parser.add_argument(
        "--i-know-what-im-doing",
        action="store_true",
        dest="live_confirmed",
        default=False,
        help="Required for --mode live. Confirms you accept real order placement risk.",
    )
    args = parser.parse_args()

    # Step 1: Load config (before setup_logger so we know the log level)
    settings = load_settings()

    # Step 2: Configure logging (must happen before any logger.* calls)
    setup_logger(settings.log_level)

    # Step 3: Log startup config (without secrets)
    log_config(settings)

    # Paper/live mode: short-circuit to run_paper_or_live()
    if args.mode in ("paper", "live"):
        # Live mode safety gate
        if args.mode == "live":
            if not args.live_confirmed:
                logger.error(
                    "LIVE MODE REQUIRES: --i-know-what-im-doing flag. "
                    "This flag confirms you accept real order placement risk. "
                    "Example: python run.py --mode live --i-know-what-im-doing"
                )
                sys.exit(1)

        # Instantiate strategy (same as mock/replay)
        if args.strategy == "momentum":
            strategy = MomentumStrategy(
                short_window=5,
                long_window=settings.rolling_window,
            )
            logger.info("STRATEGY: MomentumStrategy | short_window=5 | long_window={w}", w=settings.rolling_window)
        else:
            strategy = MeanReversionStrategy(
                window=settings.rolling_window,
                z_entry=settings.z_entry_threshold,
                z_exit=settings.z_exit_threshold,
            )
            logger.info(
                "STRATEGY: MeanReversionStrategy | window={w} | z_entry={ze} | z_exit={zx}",
                w=settings.rolling_window,
                ze=settings.z_entry_threshold,
                zx=settings.z_exit_threshold,
            )

        # Instantiate RiskManager
        risk_manager = RiskManager(
            initial_capital=settings.initial_capital,
            max_position_size=settings.max_position_size,
            daily_loss_limit=settings.daily_loss_limit,
            stop_loss_pct=settings.stop_loss_pct,
            cooldown_seconds=settings.cooldown_seconds,
        )

        # Instantiate client
        if args.mode == "live":
            from polymarket_bot.client import PolymarketLiveClient
            client = PolymarketLiveClient(settings)
            _run_live_preflight(client, settings)
        else:
            from polymarket_bot.client import PolymarketClient
            client = PolymarketClient()

        run_paper_or_live(client, strategy, risk_manager, settings, live=(args.mode == "live"))
        return

    # Backtest mode: short-circuit before client instantiation
    if args.mode == "backtest":
        run_backtest(args, settings)
        return

    # Step 4: Instantiate client based on mode
    if args.mode == "replay":
        from polymarket_bot.client import ReplayClient
        snapshot_path = find_latest_snapshot(settings.snapshot_dir)
        if snapshot_path is None:
            logger.error(
                "REPLAY mode requires a snapshot file in '{dir}'. "
                "Run: python scripts/capture.py",
                dir=settings.snapshot_dir,
            )
            sys.exit(1)
        logger.info("REPLAY mode: loading snapshot '{path}'", path=snapshot_path)
        client = ReplayClient(snapshot_path)
    else:
        from polymarket_bot.client import MockClient
        logger.info("MOCK mode: generating synthetic market data")
        client = MockClient()

    # Step 5: Instantiate strategy with settings
    if args.strategy == "momentum":
        strategy = MomentumStrategy(
            short_window=5,
            long_window=settings.rolling_window,
        )
        logger.info("STRATEGY: MomentumStrategy | short_window=5 | long_window={w}", w=settings.rolling_window)
    else:
        strategy = MeanReversionStrategy(
            window=settings.rolling_window,
            z_entry=settings.z_entry_threshold,
            z_exit=settings.z_exit_threshold,
        )
        logger.info(
            "STRATEGY: MeanReversionStrategy | window={w} | z_entry={ze} | z_exit={zx}",
            w=settings.rolling_window,
            ze=settings.z_entry_threshold,
            zx=settings.z_exit_threshold,
        )

    # Step 5b: Instantiate RiskManager with settings
    risk_manager = RiskManager(
        initial_capital=settings.initial_capital,
        max_position_size=settings.max_position_size,
        daily_loss_limit=settings.daily_loss_limit,
        stop_loss_pct=settings.stop_loss_pct,
        cooldown_seconds=settings.cooldown_seconds,
    )

    # Step 6: Run the main loop
    run_loop(client, strategy, risk_manager)


if __name__ == "__main__":
    main()
