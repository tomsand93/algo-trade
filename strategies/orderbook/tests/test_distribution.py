"""
Unit tests for orderbook distribution models.
Pure math — no network, no file I/O, no broker.

Run from orderbook/:
    python -m pytest tests/test_distribution.py -v
"""
import math
import pytest

from orderbook_strategy.distribution import (
    NormalDist,
    HistogramDist,
    ConditionalDist,
    compute_horizon_return,
)


# ── compute_horizon_return ────────────────────────────────────────────────────

class TestComputeHorizonReturn:

    def test_equal_prices_zero_return(self):
        assert compute_horizon_return(100.0, 100.0) == pytest.approx(0.0)

    def test_doubling_returns_log2(self):
        assert compute_horizon_return(100.0, 200.0) == pytest.approx(math.log(2), rel=1e-9)

    def test_halving_returns_negative_log2(self):
        assert compute_horizon_return(200.0, 100.0) == pytest.approx(-math.log(2), rel=1e-9)

    def test_zero_start_price_returns_zero(self):
        """Guard: log of 0/x is undefined — should return 0.0 safely."""
        assert compute_horizon_return(0.0, 100.0) == 0.0

    def test_zero_end_price_returns_zero(self):
        assert compute_horizon_return(100.0, 0.0) == 0.0

    def test_10pct_move(self):
        """10% up move: log(110/100) ≈ 0.09531."""
        result = compute_horizon_return(100.0, 110.0)
        assert result == pytest.approx(math.log(1.1), rel=1e-9)


# ── NormalDist (Welford's online algorithm) ───────────────────────────────────

class TestNormalDist:

    def test_single_sample_mean(self):
        d = NormalDist()
        d.update(5.0)
        assert d.mean == pytest.approx(5.0)
        assert d.n    == 1

    def test_two_samples_mean(self):
        d = NormalDist()
        d.update(2.0)
        d.update(4.0)
        assert d.mean == pytest.approx(3.0)

    def test_five_samples_correct_mean(self):
        d = NormalDist()
        for x in [1.0, 2.0, 3.0, 4.0, 5.0]:
            d.update(x)
        assert d.mean == pytest.approx(3.0)

    def test_variance_known_dataset(self):
        """Sample variance of [2,4,4,4,5,5,7,9] = 4.5714..."""
        d = NormalDist()
        for x in [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]:
            d.update(x)
        assert d.mean     == pytest.approx(5.0)
        assert d.variance == pytest.approx(4.5714, rel=1e-3)

    def test_single_sample_variance_is_zero(self):
        d = NormalDist()
        d.update(42.0)
        assert d.variance == 0.0

    def test_std_is_sqrt_variance(self):
        d = NormalDist()
        for x in [2.0, 4.0, 6.0]:
            d.update(x)
        assert d.std == pytest.approx(math.sqrt(d.variance), rel=1e-9)

    def test_p_up_plus_p_down_equals_one(self):
        d = NormalDist()
        for x in [1.0, 2.0, 3.0, 4.0, 5.0]:
            d.update(x)
        assert d.p_up() + d.p_down() == pytest.approx(1.0, rel=1e-6)

    def test_positive_mean_gives_high_p_up(self):
        d = NormalDist()
        for x in [1.5, 2.0, 1.8, 2.2, 1.9]:
            d.update(x)
        assert d.p_up() > 0.90

    def test_negative_mean_gives_high_p_down(self):
        d = NormalDist()
        for x in [-1.5, -2.0, -1.8, -2.2, -1.9]:
            d.update(x)
        assert d.p_down() > 0.90

    def test_zero_samples_returns_half(self):
        d = NormalDist()
        assert d.p_up()   == pytest.approx(0.5)
        assert d.p_down() == pytest.approx(0.5)

    def test_one_sample_returns_half(self):
        """Not enough data to estimate direction."""
        d = NormalDist()
        d.update(10.0)
        assert d.p_up()   == pytest.approx(0.5)
        assert d.p_down() == pytest.approx(0.5)

    def test_symmetric_distribution_near_half(self):
        """Symmetric samples around 0 → p_up ≈ 0.5."""
        d = NormalDist()
        for x in [-2.0, -1.0, 0.0, 1.0, 2.0]:
            d.update(x)
        assert abs(d.p_up() - 0.5) < 0.05

    def test_incremental_update_matches_batch(self):
        """Welford's result matches batch mean/variance for same samples."""
        samples = [3.1, 2.7, 4.2, 3.8, 3.5, 2.9, 4.1]
        d = NormalDist()
        for x in samples:
            d.update(x)
        batch_mean = sum(samples) / len(samples)
        n = len(samples)
        batch_var  = sum((x - batch_mean) ** 2 for x in samples) / (n - 1)
        assert d.mean     == pytest.approx(batch_mean, rel=1e-9)
        assert d.variance == pytest.approx(batch_var,  rel=1e-9)


# ── HistogramDist ─────────────────────────────────────────────────────────────

class TestHistogramDist:

    def test_p_up_plus_p_down_sums_to_one(self):
        d = HistogramDist()
        for x in range(-5, 6):
            d.update(float(x))
        total = d.p_up() + d.p_down()
        # Histogram CDF can have a small gap at exactly 0; allow ±0.05
        assert abs(total - 1.0) < 0.05

    def test_all_positive_samples_gives_low_p_down(self):
        d = HistogramDist()
        for x in [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0]:
            d.update(x)
        assert d.p_down() < 0.1

    def test_all_negative_samples_gives_high_p_down(self):
        d = HistogramDist()
        for x in [-1.0, -2.0, -3.0, -4.0, -5.0, -6.0, -7.0, -8.0, -9.0, -10.0, -11.0]:
            d.update(x)
        assert d.p_down() > 0.9

    def test_empty_returns_half(self):
        d = HistogramDist()
        assert d.p_up()   == pytest.approx(0.5)
        assert d.p_down() == pytest.approx(0.5)


# ── ConditionalDist state bucketing ──────────────────────────────────────────

class TestConditionalDistStateKey:

    def setup_method(self):
        self.dist = ConditionalDist(dist_type="normal")

    def test_pos_imbalance_pos_delta(self):
        assert self.dist.get_state_key(0.5,  0.3) == "pos_pos"

    def test_neg_imbalance_neg_delta(self):
        assert self.dist.get_state_key(-0.2, -0.1) == "neg_neg"

    def test_pos_imbalance_neg_delta(self):
        assert self.dist.get_state_key(0.5, -0.3) == "pos_neg"

    def test_neg_imbalance_pos_delta(self):
        assert self.dist.get_state_key(-0.5, 0.3) == "neg_pos"

    def test_zero_imbalance_gives_zero_prefix(self):
        assert self.dist.get_state_key(0.0, 0.3) == "zero_pos"

    def test_zero_delta_gives_zero_suffix(self):
        assert self.dist.get_state_key(0.5, 0.0) == "pos_zero"

    def test_conditioning_disabled_returns_global(self):
        dist = ConditionalDist(dist_type="normal", use_conditioning=False)
        assert dist.get_state_key(0.5, 0.3) == "global"


class TestConditionalDistUpdates:

    def test_global_receives_all_samples(self):
        dist = ConditionalDist(dist_type="normal")
        dist.update(0.01, "pos_pos")
        dist.update(-0.01, "neg_neg")
        dist.update(0.02, "pos_pos")
        assert dist._global.n == 3

    def test_state_specific_receives_own_samples_only(self):
        dist = ConditionalDist(dist_type="normal")
        dist.update(0.01, "pos_pos")
        dist.update(-0.01, "neg_neg")
        dist.update(0.02, "pos_pos")
        assert dist._states["pos_pos"].n == 2
        assert dist._states["neg_neg"].n == 1

    def test_new_state_created_on_first_update(self):
        dist = ConditionalDist(dist_type="normal")
        assert "pos_pos" not in dist._states
        dist.update(0.01, "pos_pos")
        assert "pos_pos" in dist._states

    def test_unknown_dist_type_raises(self):
        with pytest.raises(ValueError):
            ConditionalDist(dist_type="unknown")

    def test_get_probabilities_uses_global_when_state_absent(self):
        dist = ConditionalDist(dist_type="normal")
        for x in [0.01, 0.02, -0.01, 0.03, -0.02]:
            dist.update(x, "pos_pos")
        p_up, p_down, key, n = dist.get_probabilities(imbalance=-1.0, delta=-1.0)
        # "neg_neg" has no samples — should fall back to global
        assert key == "neg_neg"
        assert n == dist._global.n  # fell back to global sample count
