"""
Unit tests for PatternDetector confluence sub-components.
Tests the pure-function methods that don't need indicator recomputation.

Run from candlestick-pro/:
    python -m pytest tests/test_patterns_unit.py -v
"""
import math
import pytest
from src.models import Direction
from src.patterns import PatternDetector


def make_ema_list(value: float, length: int = 6) -> list:
    """Build list of length `length` with NaN leading up to final `value`."""
    return [math.nan] * (length - 1) + [value]


# ── _check_trend_alignment ────────────────────────────────────────────────────

class TestCheckTrendAlignment:

    def setup_method(self):
        self.det = PatternDetector()

    def test_long_both_aligned_score_one(self):
        """price > EMA21 AND EMA9 > EMA21 → fully aligned, score=1.0."""
        aligned, score = self.det._check_trend_alignment(
            Direction.LONG, price=110.0,
            ema9=make_ema_list(105.0), ema21=make_ema_list(100.0), i=5
        )
        assert aligned is True
        assert score == pytest.approx(1.0)

    def test_long_one_condition_partial_score(self):
        """price > EMA21 but EMA9 < EMA21 → partial, score=0.6."""
        aligned, score = self.det._check_trend_alignment(
            Direction.LONG, price=105.0,
            ema9=make_ema_list(98.0), ema21=make_ema_list(100.0), i=5
        )
        assert aligned is True
        assert score == pytest.approx(0.6)

    def test_long_counter_trend_rejected(self):
        """price < EMA21 AND EMA9 < EMA21 → counter-trend, rejected."""
        aligned, score = self.det._check_trend_alignment(
            Direction.LONG, price=90.0,
            ema9=make_ema_list(95.0), ema21=make_ema_list(100.0), i=5
        )
        assert aligned is False
        assert score == pytest.approx(0.0)

    def test_short_both_aligned_score_one(self):
        """price < EMA21 AND EMA9 < EMA21 → fully aligned short."""
        aligned, score = self.det._check_trend_alignment(
            Direction.SHORT, price=90.0,
            ema9=make_ema_list(95.0), ema21=make_ema_list(100.0), i=5
        )
        assert aligned is True
        assert score == pytest.approx(1.0)

    def test_short_counter_trend_rejected(self):
        """price > EMA21 AND EMA9 > EMA21 → counter-trend for short."""
        aligned, score = self.det._check_trend_alignment(
            Direction.SHORT, price=110.0,
            ema9=make_ema_list(105.0), ema21=make_ema_list(100.0), i=5
        )
        assert aligned is False
        assert score == pytest.approx(0.0)

    def test_missing_data_passes_neutral(self):
        """Empty lists → no filter, return neutral 0.5."""
        aligned, score = self.det._check_trend_alignment(
            Direction.LONG, price=100.0, ema9=[], ema21=[], i=0
        )
        assert aligned is True
        assert score == pytest.approx(0.5)

    def test_nan_values_pass_neutral(self):
        """NaN in EMA → treat as no data, pass with 0.5."""
        aligned, score = self.det._check_trend_alignment(
            Direction.LONG, price=100.0,
            ema9=[math.nan], ema21=[math.nan], i=0
        )
        assert aligned is True
        assert score == pytest.approx(0.5)

    def test_strict_mode_requires_both_conditions(self):
        """In strict mode, only one aligned condition → rejected."""
        aligned, _ = self.det._check_trend_alignment(
            Direction.LONG, price=105.0,
            ema9=make_ema_list(98.0), ema21=make_ema_list(100.0),
            i=5, strict=True
        )
        assert aligned is False

    def test_strict_mode_both_aligned_passes(self):
        """In strict mode, both conditions met → passes."""
        aligned, score = self.det._check_trend_alignment(
            Direction.LONG, price=110.0,
            ema9=make_ema_list(105.0), ema21=make_ema_list(100.0),
            i=5, strict=True
        )
        assert aligned is True
        assert score == pytest.approx(1.0)


# ── _check_volume ─────────────────────────────────────────────────────────────

class TestCheckVolume:

    def setup_method(self):
        self.det = PatternDetector()

    def test_high_volume_passes(self):
        """Volume ratio ≥ 1.2 → passes, score > 0.6."""
        ok, score = self.det._check_volume(make_ema_list(1.5), i=5)
        assert ok    is True
        assert score >  0.6

    def test_exactly_at_threshold_passes(self):
        """Volume ratio = 1.2 (minimum) → passes."""
        ok, score = self.det._check_volume(make_ema_list(1.2), i=5)
        assert ok is True

    def test_very_high_volume_score_capped_at_one(self):
        ok, score = self.det._check_volume(make_ema_list(5.0), i=5)
        assert ok    is True
        assert score <= 1.0

    def test_low_volume_fails(self):
        """Volume ratio < 1.2 → fails."""
        ok, score = self.det._check_volume(make_ema_list(0.8), i=5)
        assert ok    is False
        assert score == pytest.approx(0.0)

    def test_empty_list_passes_neutral(self):
        ok, score = self.det._check_volume([], i=0)
        assert ok    is True
        assert score == pytest.approx(0.5)

    def test_nan_passes_neutral(self):
        ok, score = self.det._check_volume([math.nan], i=0)
        assert ok    is True
        assert score == pytest.approx(0.5)


# ── _check_rsi ────────────────────────────────────────────────────────────────

class TestCheckRsi:

    def setup_method(self):
        self.det = PatternDetector()

    def test_long_rsi_in_valid_range(self):
        """RSI 40 is in [30, 60] for longs → passes."""
        ok, score = self.det._check_rsi(Direction.LONG, make_ema_list(40.0), i=5)
        assert ok    is True
        assert 0.6 <= score <= 1.0

    def test_long_rsi_overbought_fails(self):
        """RSI 75 > 60 → rejects long."""
        ok, score = self.det._check_rsi(Direction.LONG, make_ema_list(75.0), i=5)
        assert ok is False

    def test_long_rsi_oversold_fails(self):
        """RSI 20 < 30 → also rejects (not in valid range)."""
        ok, score = self.det._check_rsi(Direction.LONG, make_ema_list(20.0), i=5)
        assert ok is False

    def test_short_rsi_in_valid_range(self):
        """RSI 55 is in [40, 70] for shorts → passes."""
        ok, score = self.det._check_rsi(Direction.SHORT, make_ema_list(55.0), i=5)
        assert ok is True

    def test_short_rsi_oversold_fails(self):
        """RSI 25 < 40 for short → fails."""
        ok, score = self.det._check_rsi(Direction.SHORT, make_ema_list(25.0), i=5)
        assert ok is False

    def test_short_rsi_overbought_fails(self):
        """RSI 80 > 70 for short → fails."""
        ok, score = self.det._check_rsi(Direction.SHORT, make_ema_list(80.0), i=5)
        assert ok is False

    def test_empty_list_passes_neutral(self):
        ok, score = self.det._check_rsi(Direction.LONG, [], i=0)
        assert ok    is True
        assert score == pytest.approx(0.5)

    def test_nan_passes_neutral(self):
        ok, score = self.det._check_rsi(Direction.LONG, [math.nan], i=0)
        assert ok    is True
        assert score == pytest.approx(0.5)


# ── _calculate_confluence_confidence ─────────────────────────────────────────

class TestCalculateConfluenceConfidence:

    def setup_method(self):
        self.det = PatternDetector()

    def test_all_perfect_scores_give_one(self):
        conf = self.det._calculate_confluence_confidence(
            geometry_score=1.0, trend_score=1.0, context_score=1.0,
            volume_score=1.0,   rsi_score=1.0,
        )
        assert conf == pytest.approx(1.0)

    def test_all_zero_scores_give_zero(self):
        conf = self.det._calculate_confluence_confidence(
            geometry_score=0.0, trend_score=0.0, context_score=0.0,
            volume_score=0.0,   rsi_score=0.0,
        )
        assert conf == pytest.approx(0.0)

    def test_weights_sum_correctly(self):
        """25% geometry + 25% trend + 25% context + 15% volume + 10% RSI = 100%."""
        conf = self.det._calculate_confluence_confidence(
            geometry_score=1.0, trend_score=0.0, context_score=0.0,
            volume_score=0.0,   rsi_score=0.0,
        )
        assert conf == pytest.approx(0.25)

    def test_confidence_clamped_to_one(self):
        """Scores above 1.0 should still yield at most 1.0."""
        conf = self.det._calculate_confluence_confidence(
            geometry_score=2.0, trend_score=2.0, context_score=2.0,
            volume_score=2.0,   rsi_score=2.0,
        )
        assert conf <= 1.0

    def test_confidence_never_negative(self):
        conf = self.det._calculate_confluence_confidence(
            geometry_score=-1.0, trend_score=-1.0, context_score=-1.0,
            volume_score=-1.0,   rsi_score=-1.0,
        )
        assert conf >= 0.0
