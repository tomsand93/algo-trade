"""
Multi-Account Strategy Manager - Main entry point.

Runs paper trading strategies concurrently with an optional dashboard.
"""

import argparse
import asyncio
import logging
import msvcrt
import os
import signal
import sys
from pathlib import Path

from src.common.config import SecurityError, build_default_config
from src.common.logging_setup import setup_logging
from src.dashboard.app import start_dashboard_thread
from src.manager.engine import ManagerEngine


def parse_args():
    parser = argparse.ArgumentParser(description="Multi-Account Strategy Manager")
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Run manager without the web dashboard",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Generate daily report from last saved state and exit",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Dashboard port (default: 8050)",
    )
    return parser.parse_args()


def load_environment() -> None:
    """Load the local .env file if present."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        print("[WARN] python-dotenv not installed; using system environment variables")
        return

    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[OK] Loaded .env from {env_path}")
    else:
        print("[WARN] No .env file found; using system environment variables")


async def run_manager(config, no_dashboard: bool = False):
    """Main async entry: start engine and dashboard."""
    engine = ManagerEngine(config)

    loop = asyncio.get_event_loop()
    shutdown_event = asyncio.Event()

    def _signal_handler():
        log.info("Shutdown signal received...")
        shutdown_event.set()

    if sys.platform == "win32":
        def _win_handler(sig, frame):
            shutdown_event.set()
        signal.signal(signal.SIGINT, _win_handler)
        signal.signal(signal.SIGTERM, _win_handler)
    else:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _signal_handler)

    await engine.start()

    if not no_dashboard:
        start_dashboard_thread(
            get_data_fn=engine.get_dashboard_data,
            port=config.dashboard_port,
        )
        log.info("Dashboard available at http://localhost:%d", config.dashboard_port)

    log.info("Manager running. Press Ctrl+C to stop.")
    await shutdown_event.wait()
    await engine.shutdown()


def _acquire_lock() -> object:
    """Acquire an exclusive lock file to prevent multiple instances."""
    lock_path = Path(__file__).parent / "data" / "manager.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fh = open(lock_path, "w")
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        fh.write(str(os.getpid()))
        fh.flush()
        return fh
    except (OSError, IOError):
        print("[ERROR] Another instance of the manager is already running.")
        print("        Kill it first or delete data/manager.lock if stale.")
        sys.exit(1)


def main():
    args = parse_args()
    load_environment()

    lock_fh = None
    if not args.report_only:
        lock_fh = _acquire_lock()

    setup_logging()
    global log
    log = logging.getLogger("manager")

    log.info("=" * 70)
    log.info("  Multi-Account Strategy Manager")
    log.info("  PAPER TRADING ONLY - Live endpoints are BLOCKED")
    log.info("=" * 70)

    try:
        config = build_default_config()
    except (EnvironmentError, SecurityError) as exc:
        log.error("Configuration error: %s", exc)
        log.error("Please check your .env file or environment variables.")
        sys.exit(1)

    if args.port:
        config.dashboard_port = args.port

    if args.report_only:
        from src.storage.persistence import StatePersistence

        persistence = StatePersistence(data_dir=config.state_dir)
        state = persistence.load_state()
        if state:
            log.info("Loaded state from disk")
            log.info("Combined equity: $%.2f", state.get("combined", {}).get("total_equity", 0))
        else:
            log.info("No saved state found.")
        return

    try:
        asyncio.run(run_manager(config, no_dashboard=args.no_dashboard))
    except KeyboardInterrupt:
        log.info("Interrupted by user.")
    finally:
        if lock_fh:
            lock_fh.close()


if __name__ == "__main__":
    main()
