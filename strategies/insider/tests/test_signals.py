"""
Unit tests for signal generation.
"""
import pytest
from datetime import date
from decimal import Decimal

from src.normalize.schema import InsiderTransaction, InsiderSignal
from src.signals.single_buy_threshold import SingleBuyThresholdSignal


class TestInsiderTransaction:
    """Test InsiderTransaction schema."""

    def test_create_transaction(self):
        txn = InsiderTransaction(
            ticker="AAPL",
            insider_name="John Doe",
            transaction_date=date(2024, 1, 15),
            filing_date=date(2024, 1, 17),
            transaction_code="P",
            transaction_type="A",
            shares=Decimal("1000"),
            price_per_share=Decimal("150.00"),
            total_value=None,
        )

        assert txn.ticker == "AAPL"
        assert txn.value_usd == Decimal("150000")

    def test_is_open_market_buy(self):
        buy_txn = InsiderTransaction(
            ticker="AAPL",
            insider_name="John Doe",
            transaction_date=date(2024, 1, 15),
            filing_date=date(2024, 1, 17),
            transaction_code="P",  # Purchase
            transaction_type="A",  # Acquisition
            shares=Decimal("1000"),
            price_per_share=Decimal("150.00"),
            total_value=None,
        )

        assert buy_txn.is_open_market_buy is True

    def test_not_open_market_buy_sale(self):
        sale_txn = InsiderTransaction(
            ticker="AAPL",
            insider_name="John Doe",
            transaction_date=date(2024, 1, 15),
            filing_date=date(2024, 1, 17),
            transaction_code="S",  # Sale
            transaction_type="A",
            shares=Decimal("1000"),
            price_per_share=Decimal("150.00"),
            total_value=None,
        )

        assert sale_txn.is_open_market_buy is False

    def test_not_open_market_buy_disposition(self):
        disp_txn = InsiderTransaction(
            ticker="AAPL",
            insider_name="John Doe",
            transaction_date=date(2024, 1, 15),
            filing_date=date(2024, 1, 17),
            transaction_code="P",
            transaction_type="D",  # Disposition
            shares=Decimal("1000"),
            price_per_share=Decimal("150.00"),
            total_value=None,
        )

        assert disp_txn.is_open_market_buy is False


class TestSingleBuyThresholdSignal:
    """Test SingleBuyThresholdSignal signal generation."""

    def test_single_buy_passes(self):
        """Exactly one buy should generate a signal."""
        signal_gen = SingleBuyThresholdSignal(
            threshold_usd=Decimal("100000"),
            min_dvol=None,
            price_provider=None,
            require_prices=False,
        )

        transactions = [
            InsiderTransaction(
                ticker="AAPL",
                insider_name="John Doe",
                transaction_date=date(2024, 1, 15),
                filing_date=date(2024, 1, 17),
                transaction_code="P",
                transaction_type="A",
                shares=Decimal("1000"),
                price_per_share=Decimal("150.00"),
                total_value=None,
            )
        ]

        signals = signal_gen.generate_signals(transactions)

        assert len(signals) == 1
        assert signals[0].ticker == "AAPL"
        assert signals[0].buy_value_usd == Decimal("150000")

    def test_multiple_bys_same_day_skipped(self):
        """Multiple buys on same ticker/day should be skipped when require_single_buyer=True."""
        signal_gen = SingleBuyThresholdSignal(
            threshold_usd=Decimal("100000"),
            min_dvol=None,
            price_provider=None,
            require_prices=False,
            require_single_buyer=True,
        )

        transactions = [
            InsiderTransaction(
                ticker="AAPL",
                insider_name="John Doe",
                transaction_date=date(2024, 1, 15),
                filing_date=date(2024, 1, 17),
                transaction_code="P",
                transaction_type="A",
                shares=Decimal("1000"),
                price_per_share=Decimal("150.00"),
                total_value=None,
            ),
            InsiderTransaction(
                ticker="AAPL",
                insider_name="Jane Smith",
                transaction_date=date(2024, 1, 15),
                filing_date=date(2024, 1, 17),
                transaction_code="P",
                transaction_type="A",
                shares=Decimal("500"),
                price_per_share=Decimal("150.00"),
                total_value=None,
            ),
        ]

        signals = signal_gen.generate_signals(transactions)

        assert len(signals) == 0
        assert signal_gen.stats["skipped_multiple_buys"] == 1

    def test_below_threshold_skipped(self):
        """Buys below threshold should be skipped."""
        signal_gen = SingleBuyThresholdSignal(
            threshold_usd=Decimal("100000"),
            min_dvol=None,
            price_provider=None,
            require_prices=False,
        )

        transactions = [
            InsiderTransaction(
                ticker="AAPL",
                insider_name="John Doe",
                transaction_date=date(2024, 1, 15),
                filing_date=date(2024, 1, 17),
                transaction_code="P",
                transaction_type="A",
                shares=Decimal("100"),
                price_per_share=Decimal("150.00"),
                total_value=None,
            )
        ]

        signals = signal_gen.generate_signals(transactions)

        assert len(signals) == 0
        assert signal_gen.stats["skipped_below_threshold"] == 1

    def test_different_tickers_same_day(self):
        """Different tickers on same day should both generate signals."""
        signal_gen = SingleBuyThresholdSignal(
            threshold_usd=Decimal("100000"),
            min_dvol=None,
            price_provider=None,
            require_prices=False,
        )

        transactions = [
            InsiderTransaction(
                ticker="AAPL",
                insider_name="John Doe",
                transaction_date=date(2024, 1, 15),
                filing_date=date(2024, 1, 17),
                transaction_code="P",
                transaction_type="A",
                shares=Decimal("1000"),
                price_per_share=Decimal("150.00"),
                total_value=None,
            ),
            InsiderTransaction(
                ticker="MSFT",
                insider_name="Jane Smith",
                transaction_date=date(2024, 1, 15),
                filing_date=date(2024, 1, 17),
                transaction_code="P",
                transaction_type="A",
                shares=Decimal("1000"),
                price_per_share=Decimal("400.00"),
                total_value=None,
            ),
        ]

        signals = signal_gen.generate_signals(transactions)

        assert len(signals) == 2
        tickers = {s.ticker for s in signals}
        assert tickers == {"AAPL", "MSFT"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
