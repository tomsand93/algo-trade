"""
Scheduler for paper trading bot.

Runs the bot periodically to:
1. Fetch new insider signals
2. Process entries
3. Monitor positions
4. Log status
"""
import logging
import signal
import sys
import time
import json
from datetime import datetime, date, time as dt_time
from decimal import Decimal
from pathlib import Path
from typing import Optional

from .alpaca_paper import AlpacaPaperClient, validate_paper_mode
from .order_manager import OrderManager
from .risk_checks import RiskManager
from ..signals.single_buy_threshold import SingleBuyThresholdSignal
from ..data.price_provider import get_price_provider
from ..data.sec_api_client import SECAPIClient
from ..normalize.form4_parser import normalize_transactions

logger = logging.getLogger(__name__)


class PaperTradingBot:
    """
    Automated paper trading bot.

    Runs continuously, processing signals and monitoring positions.
    """

    def __init__(
        self,
        config: dict,
        state_file: str = "data/bot_state.json",
        log_file: Optional[str] = None,
    ):
        """
        Initialize paper trading bot.

        Args:
            config: Configuration dictionary
            state_file: Path to save/load bot state
            log_file: Path to log file
        """
        self.config = config
        self.state_file = state_file

        # Setup logging
        if log_file:
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                handlers=[
                    logging.FileHandler(log_file),
                    logging.StreamHandler(),
                ]
            )
        else:
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )

        # Validate paper mode
        if not validate_paper_mode():
            raise ValueError("PAPER_MODE must be set to 'true' for paper trading")

        # Initialize components
        self.client = AlpacaPaperClient()
        self.price_provider = get_price_provider(
            config.get("price_provider", "yfinance")
        )

        # Signal generator
        self.signal_gen = SingleBuyThresholdSignal(
            threshold_usd=Decimal(str(config.get("threshold_usd", 100000))),
            min_dvol=Decimal(str(config.get("min_dvol", 5000000))) if config.get("min_dvol") else None,
            price_provider=self.price_provider,
        )

        # Order manager
        self.order_manager = OrderManager(
            client=self.client,
            position_size_pct=Decimal(str(config.get("position_size_pct", 0.10))),
            max_positions=config.get("max_positions", 5),
            stop_loss_pct=Decimal(str(config.get("stop_loss_pct", 0.08))),
            take_profit_pct=Decimal(str(config.get("take_profit_pct", 0.16))),
            max_hold_bars=config.get("max_hold_bars", 60),
            dry_run=config.get("dry_run", False),
        )

        # Risk manager
        self.risk_manager = RiskManager(
            client=self.client,
            max_position_size_pct=Decimal(str(config.get("max_position_size_pct", 0.15))),
            max_total_exposure_pct=Decimal(str(config.get("max_total_exposure_pct", 0.95))),
            daily_loss_limit_pct=Decimal(str(config["daily_loss_limit_pct"])) if config.get("daily_loss_limit_pct") else None,
            max_drawdown_pct=Decimal(str(config["max_drawdown_pct"])) if config.get("max_drawdown_pct") else None,
        )

        # Load previous state
        self._load_state()

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self.running = False

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()

    def _load_state(self) -> None:
        """Load bot state from file."""
        if Path(self.state_file).exists():
            try:
                self.order_manager.load_state(self.state_file)
                logger.info(f"Loaded state from {self.state_file}")
            except Exception as e:
                logger.error(f"Failed to load state: {e}")

    def _save_state(self) -> None:
        """Save bot state to file."""
        try:
            Path(self.state_file).parent.mkdir(parents=True, exist_ok=True)
            self.order_manager.save_state(self.state_file)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def _is_trading_time(self) -> bool:
        """Check if current time is within trading hours."""
        now = datetime.now()

        # Check weekday (Mon-Fri)
        if now.weekday() >= 5:
            return False

        # Check time (9:30 AM - 4:00 PM ET)
        # For simplicity, using local time - adjust for timezone as needed
        market_open = dt_time(9, 30)
        market_close = dt_time(16, 0)
        current_time = now.time()

        return market_open <= current_time < market_close

    def _fetch_recent_signals(self) -> list:
        """
        Fetch insider signals from cached data.

        For production, this could be extended to fetch live from SEC API.
        For now, uses cached data which we know has good signals.

        Returns:
            List of InsiderSignal objects
        """
        try:
            # Use cached insider data
            cache_path = self.config.get("cache_path", "data/insider_multi_ticker.json")

            logger.info(f"Loading signals from cache: {cache_path}")

            # Load cached data
            from ..data.sec_api_client import load_cached_data
            raw_data = load_cached_data(cache_path)

            if not raw_data:
                logger.warning(f"No data found at {cache_path}")
                return []

            logger.info(f"Loaded {len(raw_data)} raw filings")

            # Normalize to InsiderTransaction objects
            transactions = normalize_transactions(raw_data, source="secapi")
            logger.info(f"Normalized {len(transactions)} transactions")

            # Generate signals using configured threshold
            # Use 2024 date range for our cached data
            signals = self.signal_gen.generate_signals(
                transactions=transactions,
                start_date=date(2024, 1, 1),
                end_date=date(2024, 12, 31)
            )

            logger.info(f"Generated {len(signals)} trading signals")
            for sig in signals[:5]:  # Log first 5
                logger.info(f"  {sig.ticker}: {sig.signal_date} - ${sig.buy_value_usd:,.0f}")

            return signals

        except Exception as e:
            logger.error(f"Error fetching signals: {e}", exc_info=True)
            return []

    def run_once(self) -> dict:
        """
        Run one iteration of the bot logic.

        Returns:
            Status dictionary
        """
        logger.info("=" * 50)
        logger.info(f"Bot run at {datetime.now()}")

        # Check if trading should be halted
        halt, reason = self.risk_manager.check_halt_trading()
        if halt:
            logger.warning(f"Trading halted: {reason}")
            return {"status": "halted", "reason": reason}

        # Monitor existing positions
        self.order_manager.monitor_positions()

        # Only process new signals during trading hours
        if self._is_trading_time():
            logger.info("Processing new signals...")

            # Fetch recent insider data from SEC API
            signals = self._fetch_recent_signals()

            # Process signals
            if signals:
                logger.info(f"Processing {len(signals)} new signals...")
                self.order_manager.process_signals(signals)
            else:
                logger.info("No new signals to process")

        else:
            logger.info("Outside trading hours - monitoring only")

        # Save state
        self._save_state()

        # Get status
        status = {
            "datetime": datetime.now().isoformat(),
            "order_manager": self.order_manager.get_status(),
            "risk_manager": self.risk_manager.get_status(),
        }

        # Log status
        logger.info(f"Positions: {status['order_manager']['managed_positions']}")
        logger.info(f"Processed signals: {status['order_manager']['processed_signals']}")

        return status

    def run(
        self,
        interval_seconds: int = 300,  # 5 minutes
        max_iterations: Optional[int] = None,
    ) -> None:
        """
        Run the bot continuously.

        Args:
            interval_seconds: Seconds between iterations
            max_iterations: Optional max iterations (for testing)
        """
        self.running = True
        iteration = 0

        logger.info(f"Starting paper trading bot (interval: {interval_seconds}s)")
        logger.info(f"Config: {json.dumps(self.config, indent=2)}")

        # Reset daily risk tracking at start
        self.risk_manager.reset_daily()

        while self.running:
            try:
                # Run one iteration
                status = self.run_once()

                # Check iteration limit
                iteration += 1
                if max_iterations and iteration >= max_iterations:
                    logger.info(f"Reached max iterations ({max_iterations})")
                    break

                # Wait for next interval
                logger.info(f"Waiting {interval_seconds}s until next run...")
                time.sleep(interval_seconds)

            except Exception as e:
                logger.error(f"Error in bot run: {e}", exc_info=True)
                # Continue running despite errors
                time.sleep(interval_seconds)

        logger.info("Bot stopped")

    def stop(self) -> None:
        """Stop the bot."""
        self.running = False
        self._save_state()
        logger.info("Bot state saved")


def main():
    """Main entry point for paper trading bot."""
    import yaml
    from decimal import Decimal

    # Load config
    config_path = sys.argv[1] if len(sys.argv) > 1 else "configs/config.yaml"
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Create and run bot
    bot = PaperTradingBot(
        config=config,
        state_file=config.get("state_file", "data/bot_state.json"),
        log_file=config.get("log_file", "logs/paper_trading.log"),
    )

    try:
        bot.run(
            interval_seconds=config.get("run_interval_seconds", 300),
            max_iterations=config.get("max_iterations"),  # None for infinite
        )
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt, shutting down...")
        bot.stop()


if __name__ == "__main__":
    main()
