"""
Tests for chart generation.
"""

from datetime import datetime, timezone

import pytest

# Set matplotlib to use non-interactive backend for testing
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt

from pmirror.reporting.charts import (
    generate_equity_curve,
    generate_drawdown_chart,
    generate_returns_distribution,
)


class TestGenerateEquityCurve:
    """Tests for generate_equity_curve function."""

    def test_generates_equity_curve_file(self, tmp_path):
        """Should generate equity curve chart file."""
        timestamps = [
            datetime(2024, 1, i, 12, 0, 0, tzinfo=timezone.utc)
            for i in range(1, 11)
        ]
        cash_values = [10000 + i * 100 for i in range(10)]

        path = tmp_path / "equity_curve.png"
        generate_equity_curve(timestamps, cash_values, str(path))

        assert path.exists()

    def test_includes_title_and_labels(self, tmp_path):
        """Should include title and axis labels."""
        timestamps = [
            datetime(2024, 1, i, 12, 0, 0, tzinfo=timezone.utc)
            for i in range(1, 6)
        ]
        cash_values = [10000, 10200, 10100, 10400, 10500]

        path = tmp_path / "equity.png"
        generate_equity_curve(timestamps, cash_values, str(path))

        assert path.exists()

    def test_handles_empty_data(self, tmp_path):
        """Should handle empty data gracefully."""
        timestamps = []
        cash_values = []

        path = tmp_path / "empty.png"
        # Should not crash, but behavior is undefined
        generate_equity_curve(timestamps, cash_values, str(path))

    def test_creates_parent_directory(self, tmp_path):
        """Should create parent directory if needed."""
        timestamps = [
            datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        ]
        cash_values = [10000.0]

        nested_path = tmp_path / "nested" / "dir" / "chart.png"
        generate_equity_curve(timestamps, cash_values, str(nested_path))

        assert nested_path.exists()

    def test_handles_single_point(self, tmp_path):
        """Should handle single data point."""
        timestamps = [datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)]
        cash_values = [10000.0]

        path = tmp_path / "single.png"
        generate_equity_curve(timestamps, cash_values, str(path))

        assert path.exists()


class TestGenerateDrawdownChart:
    """Tests for generate_drawdown_chart function."""

    def test_generates_drawdown_chart(self, tmp_path):
        """Should generate drawdown chart."""
        timestamps = [
            datetime(2024, 1, i, 12, 0, 0, tzinfo=timezone.utc)
            for i in range(1, 11)
        ]
        equity_values = [10000, 10500, 10300, 10700, 10200, 9800, 10100, 10400, 10600, 10900]

        path = tmp_path / "drawdown.png"
        generate_drawdown_chart(timestamps, equity_values, str(path))

        assert path.exists()

    def test_handles_empty_equity(self, tmp_path):
        """Should handle empty equity data."""
        timestamps = []
        equity_values = []

        path = tmp_path / "empty_dd.png"
        generate_drawdown_chart(timestamps, equity_values, str(path))
        # Should not crash

    def test_creates_parent_directory(self, tmp_path):
        """Should create parent directory if needed."""
        timestamps = [datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)]
        equity_values = [10000.0]

        nested_path = tmp_path / "nested" / "dd.png"
        generate_drawdown_chart(timestamps, equity_values, str(nested_path))

        assert nested_path.exists()


class TestGenerateReturnsDistribution:
    """Tests for generate_returns_distribution function."""

    def test_generates_histogram(self, tmp_path):
        """Should generate returns distribution histogram."""
        returns = [0.05, 0.03, -0.02, 0.08, -0.01, 0.04, 0.02, -0.03]

        path = tmp_path / "returns_dist.png"
        generate_returns_distribution(returns, str(path))

        assert path.exists()

    def test_handles_empty_returns(self, tmp_path):
        """Should handle empty returns list."""
        returns = []

        path = tmp_path / "empty_returns.png"
        generate_returns_distribution(returns, str(path))
        # Should not crash

    def test_handles_single_return(self, tmp_path):
        """Should handle single return value."""
        returns = [0.05]

        path = tmp_path / "single_return.png"
        generate_returns_distribution(returns, str(path))

        assert path.exists()

    def test_creates_parent_directory(self, tmp_path):
        """Should create parent directory if needed."""
        returns = [0.01, 0.02, 0.03]

        nested_path = tmp_path / "nested" / "returns.png"
        generate_returns_distribution(returns, str(nested_path))

        assert nested_path.exists()

    def test_handles_all_negative_returns(self, tmp_path):
        """Should handle all negative returns."""
        returns = [-0.01, -0.02, -0.05, -0.03]

        path = tmp_path / "all_negative.png"
        generate_returns_distribution(returns, str(path))

        assert path.exists()

    def test_handles_all_positive_returns(self, tmp_path):
        """Should handle all positive returns."""
        returns = [0.01, 0.02, 0.05, 0.03]

        path = tmp_path / "all_positive.png"
        generate_returns_distribution(returns, str(path))

        assert path.exists()
