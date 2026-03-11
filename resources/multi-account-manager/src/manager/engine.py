"""
Multi-Account Strategy Manager Engine.

Runs 3 strategy bots concurrently using asyncio with:
- Fault isolation: one crash doesn't affect others
- Per-account risk guardrails
- Unified metrics collection
- Periodic state persistence
- End-of-day reporting
"""

import asyncio
import logging
import signal
from datetime import datetime, date
from typing import Dict, List, Optional

from ..broker.alpaca_client import PaperBroker
from ..common.config import AccountConfig, ManagerConfig, RiskLimits
from ..common.risk_guardrails import AccountRiskState, RiskGuardrail
from ..metrics.tracker import MetricsTracker
from ..metrics.daily_report import DailyReporter
from ..storage.persistence import StatePersistence
from ..strategies.base import BaseStrategy, StrategyContext, StrategyEvent
from ..strategies.adapters.fvg_adapter import FVGAdapter
from ..strategies.adapters.tradingview_adapter import TradingViewAdapter
from ..strategies.adapters.candlestick_adapter import CandlestickAdapter

log = logging.getLogger(__name__)


def _create_adapter(account_name: str) -> BaseStrategy:
    """Factory: create the right adapter for each account."""
    adapters = {
        "tradingView": TradingViewAdapter,
        "bitcoin4H": CandlestickAdapter,
        "fvg": FVGAdapter,
    }
    cls = adapters.get(account_name)
    if not cls:
        raise ValueError(f"No adapter found for account: {account_name}")
    return cls()


class AccountRunner:
    """Manages a single account's lifecycle and periodic ticks."""

    def __init__(
        self,
        account_config: AccountConfig,
        adapter: BaseStrategy,
        broker: PaperBroker,
        risk_guardrail: RiskGuardrail,
        risk_state: AccountRiskState,
        scan_interval: int,
    ):
        self.config = account_config
        self.adapter = adapter
        self.broker = broker
        self.guardrail = risk_guardrail
        self.risk_state = risk_state
        self.scan_interval = scan_interval

        self.ctx = StrategyContext(
            account_name=account_config.name,
            broker=broker,
            initial_capital=account_config.initial_capital,
            config={
                "api_key": account_config.api_key,
                "api_secret": account_config.api_secret,
                "repo_path": account_config.strategy_repo_path,
            },
        )

        self.running = False
        self.events: List[StrategyEvent] = []
        self.error_count = 0
        self.max_consecutive_errors = 10

    async def start(self):
        """Initialize the strategy adapter."""
        log.info("[%s] Starting account runner...", self.config.name)
        try:
            await self.adapter.start(self.ctx)
            self.running = True
            log.info("[%s] Adapter started successfully", self.config.name)
        except Exception as e:
            log.error("[%s] Failed to start: %s", self.config.name, e, exc_info=True)
            self.running = False
            raise

    async def run_loop(self):
        """Main loop: call on_timer periodically with fault isolation."""
        log.info("[%s] Entering run loop (interval=%ds)", self.config.name, self.scan_interval)

        while self.running:
            try:
                # Check for new day
                if self.guardrail.check_new_day(self.risk_state):
                    equity = self.broker.get_equity()
                    self.risk_state.reset_for_new_day(equity)
                    log.info("[%s] New day — equity baseline: $%.2f", self.config.name, equity)

                # Check if halted by risk guardrails
                if self.risk_state.is_halted:
                    log.info(
                        "[%s] HALTED: %s — sleeping...",
                        self.config.name, self.risk_state.halt_reason,
                    )
                    await asyncio.sleep(self.scan_interval * 5)
                    continue

                # Update equity for risk checks
                try:
                    equity = await asyncio.get_event_loop().run_in_executor(
                        None, self.broker.get_equity
                    )
                    self.guardrail.update_equity(self.risk_state, equity)
                except Exception:
                    pass  # Non-fatal: use last known equity

                # Check if we're within daily loss limits
                if not self.guardrail.check_order_allowed(self.risk_state):
                    await asyncio.sleep(self.scan_interval)
                    continue

                # Run strategy tick
                new_events = await self.adapter.on_timer(self.ctx)
                if new_events:
                    self.events.extend(new_events)
                    # Trim to last 500 events
                    if len(self.events) > 500:
                        self.events = self.events[-500:]

                self.error_count = 0  # Reset on success

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.error_count += 1
                log.error(
                    "[%s] Error in run loop (count=%d): %s",
                    self.config.name, self.error_count, e, exc_info=True,
                )
                self.events.append(StrategyEvent(
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    account=self.config.name,
                    event_type="error",
                    message=f"Loop error #{self.error_count}: {e}",
                ))

                if self.error_count >= self.max_consecutive_errors:
                    log.error(
                        "[%s] Too many consecutive errors (%d). Pausing for 5 minutes.",
                        self.config.name, self.error_count,
                    )
                    await asyncio.sleep(300)
                    self.error_count = 0

            await asyncio.sleep(self.scan_interval)

    async def stop(self):
        """Graceful shutdown."""
        log.info("[%s] Stopping...", self.config.name)
        self.running = False
        try:
            await self.adapter.stop(self.ctx)
        except Exception as e:
            log.error("[%s] Error during stop: %s", self.config.name, e)

    def get_status(self) -> Dict:
        """Get current status snapshot."""
        try:
            return self.adapter.get_status(self.ctx)
        except Exception as e:
            log.error("[%s] Error getting status: %s", self.config.name, e)
            return {"equity": 0, "cash": 0, "error": str(e)}

    def get_recent_events(self, limit: int = 50) -> List[Dict]:
        """Get recent events for the dashboard feed."""
        recent = self.events[-limit:]
        return [
            {
                "timestamp": e.timestamp,
                "account": e.account,
                "type": e.event_type,
                "message": e.message,
            }
            for e in recent
        ]


class ManagerEngine:
    """
    Top-level engine: boots all accounts, runs them concurrently,
    tracks metrics, and serves data to the dashboard.
    """

    def __init__(self, config: ManagerConfig):
        self.config = config
        self.runners: Dict[str, AccountRunner] = {}
        self.metrics = MetricsTracker(
            list(config.accounts.keys()),
            initial_capital=5000.0,
        )
        self.reporter = DailyReporter(data_dir=config.state_dir)
        self.persistence = StatePersistence(data_dir=config.state_dir)
        self.risk_guardrail = RiskGuardrail(config.risk_limits)
        self.running = False
        self._tasks: List[asyncio.Task] = []

    async def start(self):
        """Initialize all account runners and start concurrent loops."""
        log.info("=" * 70)
        log.info("  MULTI-ACCOUNT STRATEGY MANAGER")
        log.info("  Accounts: %s", ", ".join(self.config.accounts.keys()))
        log.info("  Paper trading only — live endpoints BLOCKED")
        log.info("=" * 70)

        self.running = True

        # Initialize each account
        for name, acct_config in self.config.accounts.items():
            try:
                log.info("[%s] Initializing...", name)

                # Create broker with account-specific credentials
                broker = PaperBroker(
                    api_key=acct_config.api_key,
                    api_secret=acct_config.api_secret,
                    account_name=name,
                )

                # Create adapter
                adapter = _create_adapter(name)

                # Create risk state
                initial_equity = await asyncio.get_event_loop().run_in_executor(
                    None, broker.get_equity
                )
                risk_state = AccountRiskState(
                    account_name=name,
                    start_of_day_equity=initial_equity,
                    current_equity=initial_equity,
                )

                # Create runner
                runner = AccountRunner(
                    account_config=acct_config,
                    adapter=adapter,
                    broker=broker,
                    risk_guardrail=self.risk_guardrail,
                    risk_state=risk_state,
                    scan_interval=self.config.scan_interval_seconds,
                )

                await runner.start()
                self.runners[name] = runner

                # Initialize metrics with actual equity
                self.metrics.update_account(name, {"equity": initial_equity, "cash": initial_equity})

                log.info("[%s] Ready — equity: $%.2f", name, initial_equity)

            except Exception as e:
                log.error("[%s] FAILED to initialize: %s", name, e, exc_info=True)
                log.error("[%s] This account will be SKIPPED.", name)
                # Still add the runner so dashboard shows it (as STOPPED)
                runner.running = False
                self.runners[name] = runner

        if not self.runners:
            log.error("No accounts initialized successfully. Exiting.")
            return

        # Launch concurrent run loops
        for name, runner in self.runners.items():
            task = asyncio.create_task(
                runner.run_loop(),
                name=f"runner_{name}",
            )
            self._tasks.append(task)

        # Launch metrics collection loop
        self._tasks.append(asyncio.create_task(
            self._metrics_loop(),
            name="metrics_loop",
        ))

        # Launch state persistence loop
        self._tasks.append(asyncio.create_task(
            self._persistence_loop(),
            name="persistence_loop",
        ))

        log.info("All runners launched. Manager is active.")

    async def _metrics_loop(self):
        """Periodically collect metrics from all runners."""
        while self.running:
            try:
                for name, runner in self.runners.items():
                    status = runner.get_status()
                    self.metrics.update_account(name, status)
            except Exception as e:
                log.error("Error in metrics loop: %s", e)

            await asyncio.sleep(30)

    async def _persistence_loop(self):
        """Periodically save state to disk."""
        while self.running:
            try:
                # Save overall state
                state = {
                    "accounts": {},
                    "combined": self.metrics.get_combined_metrics(),
                }
                for name, runner in self.runners.items():
                    state["accounts"][name] = {
                        "status": runner.get_status(),
                        "risk": self.risk_guardrail.to_dict(runner.risk_state),
                        "running": runner.running,
                    }
                self.persistence.save_state(state)

                # Save events
                all_events = []
                for runner in self.runners.values():
                    all_events.extend(runner.get_recent_events(limit=100))
                all_events.sort(key=lambda e: e["timestamp"])
                self.persistence.save_events(all_events)

            except Exception as e:
                log.error("Error in persistence loop: %s", e)

            await asyncio.sleep(60)

    def get_dashboard_data(self) -> Dict:
        """Get all data needed by the dashboard in one call."""
        combined = self.metrics.get_combined_metrics()
        equity_histories = self.metrics.get_all_equity_histories()

        accounts = {}
        all_events = []

        for name, runner in self.runners.items():
            m = self.metrics.get_account_metrics(name)
            accounts[name] = {
                "metrics": m.to_dict() if m else {},
                "risk": self.risk_guardrail.to_dict(runner.risk_state),
                "running": runner.running,
            }
            all_events.extend(runner.get_recent_events(limit=30))

        all_events.sort(key=lambda e: e["timestamp"], reverse=True)

        return {
            "combined": combined,
            "accounts": accounts,
            "equity_histories": equity_histories,
            "events": all_events[:100],
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    async def generate_daily_report(self):
        """Generate and save the end-of-day report."""
        all_events = []
        for runner in self.runners.values():
            all_events.extend(runner.get_recent_events(limit=200))

        report = self.reporter.generate_report(self.metrics, all_events)
        self.reporter.save_json(report)
        self.reporter.save_csv(report)

        summary = self.reporter.print_summary(report)
        log.info(summary)
        return report

    async def shutdown(self):
        """Graceful shutdown of all runners."""
        log.info("Manager shutting down...")
        self.running = False

        # Generate final report
        try:
            await self.generate_daily_report()
        except Exception as e:
            log.error("Failed to generate final report: %s", e)

        # Stop all runners
        for name, runner in self.runners.items():
            try:
                await runner.stop()
            except Exception as e:
                log.error("[%s] Error stopping: %s", name, e)

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to finish
        await asyncio.gather(*self._tasks, return_exceptions=True)

        log.info("Manager shutdown complete.")
