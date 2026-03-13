"""Tests for MarketState, Signal, and SimulatedOrder models."""
import pytest
from datetime import datetime, timezone
from pydantic import ValidationError


def make_timestamp() -> datetime:
    return datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)


class TestMarketState:
    """MarketState: YES+NO price validation and field constraints."""

    def test_valid_exact_sum(self):
        from polymarket_bot.models import MarketState
        ms = MarketState(
            market_id="0xabc",
            question="Will BTC hit $100k?",
            yes_price=0.65,
            no_price=0.35,
            volume_24h=42000.0,
            timestamp=make_timestamp(),
        )
        assert ms.yes_price == 0.65
        assert ms.no_price == 0.35

    def test_valid_within_tolerance(self):
        """0.623 + 0.374 = 0.997 — within 1-cent tolerance."""
        from polymarket_bot.models import MarketState
        ms = MarketState(
            market_id="0xdef",
            question="Will ETH flip BTC?",
            yes_price=0.623,
            no_price=0.374,
            volume_24h=8200.0,
            timestamp=make_timestamp(),
        )
        assert ms.market_id == "0xdef"

    def test_invalid_sum_too_high(self):
        """0.5 + 0.6 = 1.1 — exceeds tolerance."""
        from polymarket_bot.models import MarketState
        with pytest.raises(ValidationError, match="expected ~1.00"):
            MarketState(
                market_id="0xbad",
                question="Bad market",
                yes_price=0.5,
                no_price=0.6,
                volume_24h=0.0,
                timestamp=make_timestamp(),
            )

    def test_invalid_sum_too_low(self):
        """0.5 + 0.4 = 0.9 — deviation of 0.1, exceeds tolerance."""
        from polymarket_bot.models import MarketState
        with pytest.raises(ValidationError, match="expected ~1.00"):
            MarketState(
                market_id="0xbad2",
                question="Bad market 2",
                yes_price=0.5,
                no_price=0.4,
                volume_24h=0.0,
                timestamp=make_timestamp(),
            )

    def test_invalid_yes_price_above_one(self):
        from polymarket_bot.models import MarketState
        with pytest.raises(ValidationError):
            MarketState(
                market_id="0xbad3",
                question="Bad market 3",
                yes_price=1.1,
                no_price=0.0,
                volume_24h=0.0,
                timestamp=make_timestamp(),
            )

    def test_invalid_negative_volume(self):
        from polymarket_bot.models import MarketState
        with pytest.raises(ValidationError):
            MarketState(
                market_id="0xbad4",
                question="Bad market 4",
                yes_price=0.5,
                no_price=0.5,
                volume_24h=-1.0,
                timestamp=make_timestamp(),
            )

    def test_repr_contains_question(self):
        from polymarket_bot.models import MarketState
        ms = MarketState(
            market_id="0xabc",
            question="Will BTC hit $100k?",
            yes_price=0.65,
            no_price=0.35,
            volume_24h=0.0,
            timestamp=make_timestamp(),
        )
        assert "Will BTC hit $100k?" in repr(ms) or "Will BTC hit $100k?" in str(ms)


class TestSignal:
    """Signal: direction, confidence [0,1], price [0,1]."""

    def test_valid_signal(self):
        from polymarket_bot.models import Signal
        sig = Signal(
            market_id="0xabc",
            direction="BUY_YES",
            confidence=0.74,
            price=0.62,
            reason="z-score=-2.3 < -2.0",
        )
        assert sig.direction == "BUY_YES"
        assert sig.confidence == 0.74

    def test_confidence_above_one_rejected(self):
        from polymarket_bot.models import Signal
        with pytest.raises(ValidationError):
            Signal(
                market_id="0xabc",
                direction="BUY_YES",
                confidence=1.1,
                price=0.62,
                reason="test",
            )

    def test_confidence_below_zero_rejected(self):
        from polymarket_bot.models import Signal
        with pytest.raises(ValidationError):
            Signal(
                market_id="0xabc",
                direction="BUY_YES",
                confidence=-0.1,
                price=0.62,
                reason="test",
            )

    def test_price_above_one_rejected(self):
        from polymarket_bot.models import Signal
        with pytest.raises(ValidationError):
            Signal(
                market_id="0xabc",
                direction="BUY_YES",
                confidence=0.5,
                price=1.5,
                reason="test",
            )

    @pytest.mark.parametrize("direction", ["BUY_YES", "BUY_NO", "SELL_YES", "SELL_NO"])
    def test_valid_directions(self, direction):
        from polymarket_bot.models import Signal
        sig = Signal(
            market_id="0xabc",
            direction=direction,
            confidence=0.5,
            price=0.5,
            reason="test",
        )
        assert sig.direction == direction


class TestSimulatedOrder:
    """SimulatedOrder: fill_price [0,1], quantity >= 0, side and direction strings, order_id, status."""

    def test_valid_order(self):
        from polymarket_bot.models import SimulatedOrder
        order = SimulatedOrder(
            market_id="0xabc",
            side="YES",
            direction="BUY",
            fill_price=0.65,
            quantity=10.0,
            timestamp=make_timestamp(),
        )
        assert order.fill_price == 0.65
        assert order.quantity == 10.0

    def test_order_id_is_auto_generated(self):
        """order_id is assigned automatically as a non-empty UUID string."""
        from polymarket_bot.models import SimulatedOrder
        order = SimulatedOrder(
            market_id="0xabc",
            side="YES",
            direction="BUY",
            fill_price=0.65,
            quantity=10.0,
            timestamp=make_timestamp(),
        )
        assert isinstance(order.order_id, str)
        assert len(order.order_id) > 0

    def test_two_orders_have_different_ids(self):
        """Each SimulatedOrder gets a unique auto-generated order_id."""
        from polymarket_bot.models import SimulatedOrder
        kwargs = dict(market_id="0xabc", side="YES", direction="BUY",
                      fill_price=0.65, quantity=10.0, timestamp=make_timestamp())
        order_a = SimulatedOrder(**kwargs)
        order_b = SimulatedOrder(**kwargs)
        assert order_a.order_id != order_b.order_id

    def test_order_id_can_be_set_explicitly(self):
        """Caller can supply a specific order_id (e.g., for cancel_order lookup)."""
        from polymarket_bot.models import SimulatedOrder
        order = SimulatedOrder(
            order_id="my-custom-id-001",
            market_id="0xabc",
            side="YES",
            direction="BUY",
            fill_price=0.65,
            quantity=10.0,
            timestamp=make_timestamp(),
        )
        assert order.order_id == "my-custom-id-001"

    def test_default_status_is_open(self):
        """New orders default to status='OPEN'."""
        from polymarket_bot.models import SimulatedOrder
        order = SimulatedOrder(
            market_id="0xabc",
            side="YES",
            direction="BUY",
            fill_price=0.65,
            quantity=10.0,
            timestamp=make_timestamp(),
        )
        assert order.status == "OPEN"

    def test_status_filled_accepted(self):
        from polymarket_bot.models import SimulatedOrder
        order = SimulatedOrder(
            market_id="0xabc",
            side="YES",
            direction="BUY",
            fill_price=0.65,
            quantity=10.0,
            status="FILLED",
            timestamp=make_timestamp(),
        )
        assert order.status == "FILLED"

    def test_status_cancelled_accepted(self):
        """Orders can be constructed with status='CANCELLED' (used by cancel_order)."""
        from polymarket_bot.models import SimulatedOrder
        order = SimulatedOrder(
            market_id="0xabc",
            side="YES",
            direction="BUY",
            fill_price=0.65,
            quantity=10.0,
            status="CANCELLED",
            timestamp=make_timestamp(),
        )
        assert order.status == "CANCELLED"

    def test_invalid_status_rejected(self):
        """Status values outside the Literal are rejected with ValidationError."""
        from polymarket_bot.models import SimulatedOrder
        with pytest.raises(ValidationError):
            SimulatedOrder(
                market_id="0xabc",
                side="YES",
                direction="BUY",
                fill_price=0.65,
                quantity=10.0,
                status="PENDING",  # not a valid Literal
                timestamp=make_timestamp(),
            )

    def test_fill_price_above_one_rejected(self):
        from polymarket_bot.models import SimulatedOrder
        with pytest.raises(ValidationError):
            SimulatedOrder(
                market_id="0xabc",
                side="YES",
                direction="BUY",
                fill_price=1.5,
                quantity=10.0,
                timestamp=make_timestamp(),
            )

    def test_negative_quantity_rejected(self):
        from polymarket_bot.models import SimulatedOrder
        with pytest.raises(ValidationError):
            SimulatedOrder(
                market_id="0xabc",
                side="YES",
                direction="BUY",
                fill_price=0.65,
                quantity=-1.0,
                timestamp=make_timestamp(),
            )
