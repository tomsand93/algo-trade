"""
Unit tests for the Candle data model.
All pure property computation — no network, no file I/O.

Run from candlestick-pro/:
    python -m pytest tests/test_models.py -v
"""
import pytest
from src.models import Candle, Direction, PatternType


class TestCandleRange:

    def test_range_is_high_minus_low(self):
        c = Candle(timestamp=0, open=100, high=105, low=95, close=102, volume=1000)
        assert c.range == pytest.approx(10.0)

    def test_range_with_equal_high_low(self):
        # Doji with very tight range
        c = Candle(timestamp=0, open=100, high=100.1, low=99.9, close=100)
        assert c.range == pytest.approx(0.2)


class TestCandleBody:

    def test_body_bullish(self):
        c = Candle(timestamp=0, open=100, high=105, low=95, close=102)
        assert c.body == pytest.approx(2.0)

    def test_body_bearish(self):
        c = Candle(timestamp=0, open=102, high=105, low=95, close=100)
        assert c.body == pytest.approx(2.0)  # absolute value

    def test_body_doji_zero(self):
        c = Candle(timestamp=0, open=100, high=105, low=95, close=100)
        assert c.body == pytest.approx(0.0)


class TestCandleWicks:

    def test_upper_wick_bullish(self):
        # close=102, high=105 → upper wick = 3
        c = Candle(timestamp=0, open=100, high=105, low=95, close=102)
        assert c.upper_wick == pytest.approx(3.0)

    def test_lower_wick_bullish(self):
        # open=100, low=95 → lower wick = 5
        c = Candle(timestamp=0, open=100, high=105, low=95, close=102)
        assert c.lower_wick == pytest.approx(5.0)

    def test_upper_wick_bearish(self):
        # open=102, high=105 → upper wick = 3
        c = Candle(timestamp=0, open=102, high=105, low=95, close=100)
        assert c.upper_wick == pytest.approx(3.0)

    def test_lower_wick_bearish(self):
        # close=100, low=95 → lower wick = 5
        c = Candle(timestamp=0, open=102, high=105, low=95, close=100)
        assert c.lower_wick == pytest.approx(5.0)

    def test_pin_bar_long_lower_wick(self):
        # Hammer: tiny body at top, long lower wick
        c = Candle(timestamp=0, open=104, high=105, low=95, close=104.5)
        assert c.lower_wick > c.upper_wick
        assert c.lower_wick == pytest.approx(9.0)

    def test_shooting_star_long_upper_wick(self):
        # Shooting star: tiny body at bottom, long upper wick
        c = Candle(timestamp=0, open=96, high=105, low=95, close=96.5)
        assert c.upper_wick > c.lower_wick


class TestCandleDirection:

    def test_bullish_when_close_above_open(self):
        c = Candle(timestamp=0, open=100, high=105, low=95, close=102)
        assert c.is_bullish is True

    def test_bearish_when_close_below_open(self):
        c = Candle(timestamp=0, open=102, high=105, low=95, close=100)
        assert c.is_bullish is False

    def test_doji_is_not_bullish(self):
        c = Candle(timestamp=0, open=100, high=105, low=95, close=100)
        assert c.is_bullish is False


class TestCandleBodyRatio:

    def test_full_body_ratio_is_one(self):
        # open=95, close=105, range=10, body=10
        c = Candle(timestamp=0, open=95, high=105, low=95, close=105)
        assert c.body_ratio == pytest.approx(1.0)

    def test_doji_body_ratio_is_zero(self):
        c = Candle(timestamp=0, open=100, high=105, low=95, close=100)
        assert c.body_ratio == pytest.approx(0.0)

    def test_half_body_ratio(self):
        # open=100, close=105, range=10 → body_ratio=0.5
        c = Candle(timestamp=0, open=100, high=105, low=95, close=105)
        # range=10, body=5
        assert c.body_ratio == pytest.approx(0.5)

    def test_body_ratio_bounded_zero_to_one(self):
        c = Candle(timestamp=0, open=100, high=110, low=90, close=107)
        assert 0.0 <= c.body_ratio <= 1.0


class TestCandleValidation:

    def test_invalid_high_below_close_raises(self):
        with pytest.raises(ValueError, match="High"):
            Candle(timestamp=0, open=100, high=99, low=95, close=100)

    def test_invalid_high_below_open_raises(self):
        with pytest.raises(ValueError, match="High"):
            Candle(timestamp=0, open=105, high=104, low=95, close=100)

    def test_invalid_low_above_open_raises(self):
        with pytest.raises(ValueError, match="Low"):
            Candle(timestamp=0, open=100, high=105, low=101, close=102)

    def test_invalid_low_above_close_raises(self):
        with pytest.raises(ValueError, match="Low"):
            Candle(timestamp=0, open=100, high=105, low=103, close=100)

    def test_negative_volume_raises(self):
        with pytest.raises(ValueError, match="Volume"):
            Candle(timestamp=0, open=100, high=105, low=95, close=102, volume=-1)

    def test_zero_volume_allowed(self):
        c = Candle(timestamp=0, open=100, high=105, low=95, close=102, volume=0)
        assert c.volume == 0

    def test_none_volume_allowed(self):
        c = Candle(timestamp=0, open=100, high=105, low=95, close=102, volume=None)
        assert c.volume is None


class TestEnums:

    def test_direction_values(self):
        assert Direction.LONG.value  == "long"
        assert Direction.SHORT.value == "short"

    def test_pattern_type_values(self):
        assert PatternType.ENGULFING.value    == "engulfing"
        assert PatternType.PIN_BAR.value      == "pin_bar"
        assert PatternType.MORNING_STAR.value == "morning_star"
        assert PatternType.EVENING_STAR.value == "evening_star"
        assert PatternType.INSIDE_BAR.value   == "inside_bar"
