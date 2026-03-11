"""
Signal generator: Single insider buy with threshold.

Per spec:
1. Only open-market insider BUYS (transaction_code == "P", acquisition)
2. EXACTLY ONE qualifying buy per ticker per date
3. Minimum dollar threshold
4. Optional liquidity filter
"""
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Tuple, Any

from ..normalize.schema import InsiderTransaction, InsiderSignal
from ..data.price_provider import get_price_provider

logger = logging.getLogger(__name__)


class SingleBuyThresholdSignal:
    """
    Generate signals based on single insider buy events with dollar threshold.

    Signal Rules:
    1. Consider ONLY open-market insider BUYS (transaction_code == "P", acquisition)
    2. For ticker T and date D, there must be EXACTLY ONE qualifying buy
    3. buy_value_usd >= THRESHOLD_USD
    4. Optional liquidity filter: avg_daily_dollar_volume_20 >= MIN_DVOL
    """

    def __init__(
        self,
        threshold_usd: Decimal = Decimal("100000"),
        min_dvol: Optional[Decimal] = None,
        price_provider: Optional[Any] = None,
        require_prices: bool = True,
    ):
        """
        Initialize signal generator.

        Args:
            threshold_usd: Minimum buy value in USD (default $100,000)
            min_dvol: Minimum average daily dollar volume (default None = no filter)
            price_provider: Price data provider for liquidity/pricing checks
            require_prices: If True, skip tickers with no price data available
        """
        self.threshold_usd = threshold_usd
        self.min_dvol = min_dvol
        self.price_provider = price_provider
        self.require_prices = require_prices

        # Track signal counts and skip reasons
        self.stats = defaultdict(int)

    def generate_signals(
        self,
        transactions: List[InsiderTransaction],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[InsiderSignal]:
        """
        Generate signals from a list of transactions.

        Args:
            transactions: List of normalized InsiderTransaction objects
            start_date: Optional filter for transaction start date
            end_date: Optional filter for transaction end date

        Returns:
            List of InsiderSignal objects
        """
        # Filter by date range if specified
        if start_date:
            transactions = [t for t in transactions if t.transaction_date >= start_date]
        if end_date:
            transactions = [t for t in transactions if t.transaction_date <= end_date]

        logger.info(f"Processing {len(transactions)} transactions")

        # Step 1: Filter to qualifying insider buys (P = open market, M = option exercise)
        qualifying_buys = [
            t for t in transactions
            if t.is_insider_buy
        ]
        logger.info(f"Found {len(qualifying_buys)} insider buys (P + M codes)")

        # Step 2: Group by ticker and transaction date
        # Use filing date as signal date if transaction date is missing
        buys_by_ticker_date: Dict[Tuple[str, date], List[InsiderTransaction]] = defaultdict(list)

        for txn in qualifying_buys:
            key = (txn.ticker, txn.transaction_date)
            buys_by_ticker_date[key].append(txn)

        # Step 3: Apply single-buy constraint
        # Keep only ticker+date pairs with EXACTLY ONE qualifying buy
        single_buy_pairs = {
            key: txns
            for key, txns in buys_by_ticker_date.items()
            if len(txns) == 1
        }

        skipped_multiple = len(buys_by_ticker_date) - len(single_buy_pairs)
        self.stats["skipped_multiple_buys"] = skipped_multiple
        logger.info(f"Single-buy pairs: {len(single_buy_pairs)}, skipped {skipped_multiple} with multiple buys")

        # Step 4: Apply threshold and liquidity filters
        signals = []

        for (ticker, txn_date), txns in single_buy_pairs.items():
            txn = txns[0]  # Only one transaction in the list

            # Check value threshold
            if txn.value_usd < self.threshold_usd:
                self.stats["skipped_below_threshold"] += 1
                continue

            # Check liquidity filter if configured
            if self.min_dvol is not None and self.price_provider is not None:
                avg_dvol = self.price_provider.calculate_avg_dollar_volume(
                    ticker,
                    lookback_days=20,
                    end_date=txn.filing_date
                )
                if avg_dvol is None or avg_dvol < self.min_dvol:
                    self.stats["skipped_liquidity"] += 1
                    logger.debug(f"{ticker} skipped: low liquidity (${avg_dvol or 0:.0f} < ${self.min_dvol:.0f})")
                    continue

            # Check price availability if required
            if self.require_prices and self.price_provider is not None:
                latest_price = self.price_provider.get_latest_price(ticker)
                if latest_price is None:
                    self.stats["skipped_no_prices"] += 1
                    logger.debug(f"{ticker} skipped: no price data available")
                    continue

            # Determine signal date (next trading day after filing)
            signal_date = self._get_next_trading_day(txn.filing_date)

            # Get price - use transaction price if available, otherwise fetch market price
            price = txn.price_per_share
            if price is None or price <= 0:
                # Option exercises often don't have price in filing - fetch market price
                if self.price_provider is not None:
                    price = self.price_provider.get_price_on_date(ticker, txn.transaction_date)
                    if price is None:
                        # Try filing date if transaction date price unavailable
                        price = self.price_provider.get_price_on_date(ticker, txn.filing_date)

                if price is None or price <= 0:
                    self.stats["skipped_no_price"] += 1
                    logger.debug(f"{ticker} skipped: no price data available")
                    continue

                logger.debug(f"{ticker} using market price ${price:.2f} (option exercise)")

            # Recalculate value if needed (for option exercises without filing price)
            value_usd = txn.value_usd
            if value_usd <= 0 and price > 0:
                value_usd = price * txn.shares

            # Check value threshold with calculated value
            if value_usd < self.threshold_usd:
                self.stats["skipped_below_threshold"] += 1
                continue

            # Create signal
            signal = InsiderSignal(
                ticker=ticker,
                signal_date=signal_date,
                transaction_date=txn.transaction_date,
                filing_date=txn.filing_date,
                buy_value_usd=value_usd,
                insider_name=txn.insider_name,
                shares=txn.shares,
                price_per_share=price,
            )
            signals.append(signal)

        logger.info(f"Generated {len(signals)} signals")
        self._log_stats()

        return signals

    def _get_next_trading_day(self, input_date: date) -> date:
        """
        Get the next trading day after the input date.

        Simple implementation: skips weekends (Saturday, Sunday).
        For production, consider using a trading calendar library.
        """
        next_date = input_date + timedelta(days=1)

        # Skip weekends
        while next_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
            next_date += timedelta(days=1)

        return next_date

    def _log_stats(self) -> None:
        """Log signal generation statistics."""
        logger.info("Signal Generation Statistics:")
        for key, value in sorted(self.stats.items()):
            logger.info(f"  {key}: {value}")


def load_transactions_and_generate_signals(
    data_path: str,
    source: str = "secapi",
    threshold_usd: Decimal = Decimal("100000"),
    min_dvol: Optional[Decimal] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[InsiderSignal]:
    """
    Convenience function to load cached transactions and generate signals.

    Args:
        data_path: Path to cached transaction data
        source: Data source format ("secapi" or "edgar")
        threshold_usd: Minimum buy value threshold
        min_dvol: Optional minimum dollar volume filter
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        List of InsiderSignal objects
    """
    from ..data.sec_api_client import load_cached_data
    from ..normalize.form4_parser import normalize_transactions

    # Load cached data
    raw_data = load_cached_data(data_path)
    if not raw_data:
        logger.warning(f"No data found at {data_path}")
        return []

    # Normalize transactions
    transactions = normalize_transactions(raw_data, source=source)
    logger.info(f"Loaded {len(transactions)} normalized transactions")

    # Generate signals
    price_provider = get_price_provider("yfinance")
    signal_gen = SingleBuyThresholdSignal(
        threshold_usd=threshold_usd,
        min_dvol=min_dvol,
        price_provider=price_provider,
    )

    return signal_gen.generate_signals(
        transactions=transactions,
        start_date=start_date,
        end_date=end_date,
    )
