"""TDD tests for polymarket_bot.metrics.

All test cases use hand-calculated expected values so failures are
immediately diagnosable without running the implementation.
"""
import math
import statistics

import pytest

from polymarket_bot.metrics import sharpe_ratio, sortino_ratio, max_drawdown, win_rate


# ---------------------------------------------------------------------------
# win_rate
# ---------------------------------------------------------------------------

class TestWinRate:
    def test_empty_list_returns_zero(self):
        assert win_rate([]) == 0.0

    def test_mixed_trades_correct_percentage(self):
        # 2 winners out of 3 → 66.666...%
        result = win_rate([1.0, -0.5, 0.5])
        assert result == pytest.approx(200 / 3, rel=0.001)

    def test_all_winners(self):
        assert win_rate([1.0, 2.0]) == 100.0

    def test_all_losers(self):
        assert win_rate([-1.0, -2.0]) == 0.0

    def test_zero_pnl_not_winner(self):
        # pnl > 0 strictly, 0.0 is not a winner
        assert win_rate([0.0, 0.0]) == 0.0

    def test_single_winner(self):
        assert win_rate([1.0]) == 100.0

    def test_single_loser(self):
        assert win_rate([-1.0]) == 0.0


# ---------------------------------------------------------------------------
# sharpe_ratio
# ---------------------------------------------------------------------------

class TestSharpeRatio:
    def test_empty_list_returns_none(self):
        assert sharpe_ratio([]) is None

    def test_single_value_returns_none(self):
        assert sharpe_ratio([1.0]) is None

    def test_all_same_value_zero_std_returns_none(self):
        # std == 0 → undefined Sharpe
        assert sharpe_ratio([1.0, 1.0, 1.0]) is None

    def test_symmetric_trades_zero_mean_returns_zero(self):
        # pnls = [1.0, -1.0, 1.0, -1.0] → mean=0.0, std=1.0
        # Sharpe = 0.0 * sqrt(252) / 1.0 = 0.0
        result = sharpe_ratio([1.0, -1.0, 1.0, -1.0])
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_known_answer(self):
        # pnls = [2.0, 1.0, 3.0]
        # mean = 2.0, stdev([2,1,3]) = 1.0
        # Sharpe = 2.0 / 1.0 * sqrt(252)
        pnls = [2.0, 1.0, 3.0]
        expected = 2.0 / statistics.stdev(pnls) * math.sqrt(252)
        result = sharpe_ratio(pnls)
        assert result == pytest.approx(expected, rel=0.001)

    def test_risk_free_rate_subtracted(self):
        # With risk_free_rate=0.5: (mean - rfr) / std * sqrt(252)
        pnls = [2.0, 1.0, 3.0]
        rfr = 0.5
        mean = statistics.mean(pnls)
        std = statistics.stdev(pnls)
        expected = (mean - rfr) / std * math.sqrt(252)
        result = sharpe_ratio(pnls, risk_free_rate=rfr)
        assert result == pytest.approx(expected, rel=0.001)


# ---------------------------------------------------------------------------
# sortino_ratio
# ---------------------------------------------------------------------------

class TestSortinoRatio:
    def test_empty_list_returns_none(self):
        assert sortino_ratio([]) is None

    def test_single_value_returns_none(self):
        assert sortino_ratio([1.0]) is None

    def test_all_winners_no_downside_returns_none(self):
        # No losing trades → downside list empty → None
        assert sortino_ratio([1.0, 2.0, 3.0]) is None

    def test_single_loser_insufficient_downside_returns_none(self):
        # Only one loser → downside stdev needs 2+ → None
        assert sortino_ratio([1.0, 2.0, -1.0]) is None

    def test_two_losers_known_answer(self):
        # pnls = [2.0, -1.0, -3.0]
        # mean = (2 - 1 - 3) / 3 = -2/3
        # downside = [-1.0, -3.0], stdev = sqrt(2) ≈ 1.41421
        # Sortino = (-2/3) / sqrt(2) * sqrt(252)
        pnls = [2.0, -1.0, -3.0]
        mean = statistics.mean(pnls)
        downside = [p for p in pnls if p < 0]
        downside_std = statistics.stdev(downside)
        expected = mean / downside_std * math.sqrt(252)
        result = sortino_ratio(pnls)
        assert result == pytest.approx(expected, rel=0.001)

    def test_zero_downside_std_returns_none(self):
        # Two identical losses → downside stdev = 0 → None
        assert sortino_ratio([1.0, -2.0, -2.0]) is None

    def test_risk_free_rate_applied(self):
        pnls = [2.0, -1.0, -3.0]
        rfr = 0.1
        mean = statistics.mean(pnls)
        downside = [p for p in pnls if p < 0]
        downside_std = statistics.stdev(downside)
        expected = (mean - rfr) / downside_std * math.sqrt(252)
        result = sortino_ratio(pnls, risk_free_rate=rfr)
        assert result == pytest.approx(expected, rel=0.001)


# ---------------------------------------------------------------------------
# max_drawdown
# ---------------------------------------------------------------------------

class TestMaxDrawdown:
    def test_empty_list_returns_zero(self):
        assert max_drawdown([]) == 0.0

    def test_single_value_returns_zero(self):
        assert max_drawdown([100.0]) == 0.0

    def test_monotonically_rising_returns_zero(self):
        assert max_drawdown([100, 110, 120]) == 0.0

    def test_monotonically_falling_known_answer(self):
        # [100, 90, 80] → peak=100, dd at 80 = (80-100)/100 = -0.20
        result = max_drawdown([100, 90, 80])
        assert result == pytest.approx(-0.20, rel=0.001)

    def test_complex_curve_known_answer(self):
        # [100, 110, 90, 120, 100]
        # After 110: dd at 90 = (90-110)/110 ≈ -0.1818
        # After 120: dd at 100 = (100-120)/120 ≈ -0.1667
        # max drawdown = -0.1818 (larger absolute loss)
        result = max_drawdown([100, 110, 90, 120, 100])
        expected = (90 - 110) / 110
        assert result == pytest.approx(expected, rel=0.001)

    def test_two_point_decline(self):
        # Simple two-point check
        result = max_drawdown([200, 150])
        expected = (150 - 200) / 200  # -0.25
        assert result == pytest.approx(expected, rel=0.001)

    def test_peak_updated_correctly(self):
        # Peak rises to 150, then drawdown from 150 to 100 = -1/3
        result = max_drawdown([100, 150, 100])
        expected = (100 - 150) / 150
        assert result == pytest.approx(expected, rel=0.001)
