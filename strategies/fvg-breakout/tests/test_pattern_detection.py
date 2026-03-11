"""
Unit tests for FVG pattern detection logic.
No network, no broker, no disk I/O — pure rule logic only.

Run from fvg-breakout/:
    python -m pytest tests/test_pattern_detection.py -v
"""
import pytest
import pandas as pd

from src.pattern_detection import (
    PatternDetector,
    DailySetup,
    validate_trading_window,
)
from src.config import StrategyConfig


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a 1-minute OHLCV DataFrame with a DatetimeIndex from compact row specs."""
    records = []
    for r in rows:
        records.append({
            "open":   r["open"],
            "high":   r["high"],
            "low":    r["low"],
            "close":  r["close"],
            "volume": r.get("volume", 1000),
        })
    idx = pd.to_datetime([f"2024-01-15 {r['time']}:00" for r in rows])
    return pd.DataFrame(records, index=idx)


def make_setup(high=101.0, low=99.0) -> DailySetup:
    return DailySetup(date="2024-01-15", symbol="AAPL",
                      day_high=high, day_low=low)


# ── validate_trading_window ───────────────────────────────────────────────────

class TestValidateTradingWindow:

    def test_mid_session_valid(self):
        assert validate_trading_window(pd.Timestamp("2024-01-15 10:30:00")) is True

    def test_exactly_at_open_boundary_valid(self):
        assert validate_trading_window(pd.Timestamp("2024-01-15 09:35:00")) is True

    def test_exactly_at_close_boundary_valid(self):
        assert validate_trading_window(pd.Timestamp("2024-01-15 16:00:00")) is True

    def test_before_session_start_invalid(self):
        assert validate_trading_window(pd.Timestamp("2024-01-15 09:30:00")) is False

    def test_after_session_end_invalid(self):
        assert validate_trading_window(pd.Timestamp("2024-01-15 16:01:00")) is False

    def test_pre_market_invalid(self):
        assert validate_trading_window(pd.Timestamp("2024-01-15 08:00:00")) is False


# ── detect_break ──────────────────────────────────────────────────────────────

class TestDetectBreak:

    def setup_method(self):
        self.det = PatternDetector()
        self.setup = make_setup(high=101.0, low=99.0)

    def test_price_above_high_is_long(self):
        assert self.det.detect_break(101.5, self.setup) == "long"

    def test_price_below_low_is_short(self):
        assert self.det.detect_break(98.5, self.setup) == "short"

    def test_price_inside_range_is_none(self):
        assert self.det.detect_break(100.0, self.setup) is None

    def test_price_exactly_at_high_no_break(self):
        # Strictly greater-than required
        assert self.det.detect_break(101.0, self.setup) is None

    def test_price_exactly_at_low_no_break(self):
        # Strictly less-than required
        assert self.det.detect_break(99.0, self.setup) is None

    def test_long_only_mode_ignores_short_break(self):
        det = PatternDetector(long_only=True)
        # Price below low would normally be short — in long_only the detect_break
        # itself still returns "short", but find_trade_setup ignores it
        # (detect_break is direction-agnostic; long_only filter is in find_trade_setup)
        result = det.detect_break(98.5, self.setup)
        assert result == "short"  # detect_break itself is not filtered


# ── detect_fvg ────────────────────────────────────────────────────────────────

class TestDetectFvg:

    def setup_method(self):
        self.det = PatternDetector(risk_reward_ratio=3.0)

    def _bullish_gap_df(self):
        """c1.high=100.5 < c3.low=101.0 → valid bullish FVG."""
        return make_df([
            {"time": "09:36", "open": 100.0, "high": 100.5, "low":  99.5, "close": 100.0},
            {"time": "09:37", "open": 101.0, "high": 103.0, "low": 100.8, "close": 102.5},
            {"time": "09:38", "open": 102.0, "high": 102.5, "low": 101.0, "close": 101.5},
        ])

    def _bearish_gap_df(self):
        """c1.low=101.5 > c3.high=101.0 → valid bearish FVG."""
        return make_df([
            {"time": "09:36", "open": 102.0, "high": 102.5, "low": 101.5, "close": 102.0},
            {"time": "09:37", "open": 101.0, "high": 101.2, "low":  99.0, "close":  99.5},
            {"time": "09:38", "open": 100.0, "high": 101.0, "low":  99.5, "close":  99.8},
        ])

    def test_bullish_fvg_detected(self):
        fvg = self.det.detect_fvg(self._bullish_gap_df(), start_idx=0, direction="long")
        assert fvg is not None
        assert fvg.direction == "long"
        assert fvg.gap_high == pytest.approx(100.5)
        assert fvg.gap_low  == pytest.approx(101.0)

    def test_bullish_fvg_entry_trigger_at_gap_low(self):
        fvg = self.det.detect_fvg(self._bullish_gap_df(), start_idx=0, direction="long")
        assert fvg.entry_trigger == pytest.approx(fvg.gap_low)

    def test_bullish_fvg_stop_below_c1_low(self):
        """Default SL placement (c1) → stop_loss = c1.low."""
        fvg = self.det.detect_fvg(self._bullish_gap_df(), start_idx=0, direction="long")
        assert fvg.stop_loss == pytest.approx(99.5)

    def test_take_profit_is_3r(self):
        fvg = self.det.detect_fvg(self._bullish_gap_df(), start_idx=0, direction="long")
        risk   = abs(fvg.entry_trigger - fvg.stop_loss)
        reward = abs(fvg.take_profit   - fvg.entry_trigger)
        assert reward == pytest.approx(risk * 3.0, rel=1e-6)

    def test_bearish_fvg_detected(self):
        fvg = self.det.detect_fvg(self._bearish_gap_df(), start_idx=0, direction="short")
        assert fvg is not None
        assert fvg.direction == "short"

    def test_no_bullish_fvg_when_gap_absent(self):
        """c3.low <= c1.high means no gap."""
        df = make_df([
            {"time": "09:36", "open": 100, "high": 102.0, "low": 99.5, "close": 100},
            {"time": "09:37", "open": 101, "high": 103.0, "low": 100.8, "close": 102.5},
            {"time": "09:38", "open": 102, "high": 102.5, "low": 101.5, "close": 101.8},
            # c3.low=101.5 <= c1.high=102.0 → no gap
        ])
        assert self.det.detect_fvg(df, start_idx=0, direction="long") is None

    def test_returns_none_on_insufficient_candles(self):
        """Need at least 3 candles starting from start_idx."""
        df = make_df([
            {"time": "09:36", "open": 100, "high": 101, "low": 99, "close": 100},
            {"time": "09:37", "open": 101, "high": 103, "low": 100, "close": 102},
        ])
        assert self.det.detect_fvg(df, start_idx=0, direction="long") is None

    def test_c2_sl_placement_tighter_stop(self):
        """With sl_placement='c2', stop is c2.low (tighter)."""
        cfg = StrategyConfig(sl_placement="c2")
        det = PatternDetector(config=cfg)
        df  = self._bullish_gap_df()
        fvg = det.detect_fvg(df, start_idx=0, direction="long")
        assert fvg is not None
        # c2.low = 100.8, which is tighter (higher) than c1.low = 99.5
        assert fvg.stop_loss == pytest.approx(100.8)


# ── DailySetup dataclass ──────────────────────────────────────────────────────

class TestDailySetup:

    def test_fields_stored_correctly(self):
        s = make_setup(high=105.5, low=103.2)
        assert s.day_high  == pytest.approx(105.5)
        assert s.day_low   == pytest.approx(103.2)
        assert s.symbol    == "AAPL"
        assert s.valid     is True

    def test_spread_is_positive(self):
        s = make_setup(high=102.0, low=98.0)
        assert s.day_high > s.day_low
