"""
Tests for markdown report generation.
"""

from datetime import datetime, timezone, timedelta

import pytest

from pmirror.reporting.report import generate_markdown_report, save_report
from pmirror.domain.models import BacktestMetrics


class TestGenerateMarkdownReport:
    """Tests for generate_markdown_report function."""

    def test_generates_basic_report(self):
        """Should generate a basic markdown report."""
        metrics = BacktestMetrics(
            total_return=0.12,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown=0.05,
            max_drawdown_duration=timedelta(0),
            total_trades=10,
            win_rate=0.6,
            avg_trade_return=0.01,
            skipped_trades=2,
            skipped_rate=0.17,
            max_exposure=5000.0,
            avg_exposure=2000.0,
            exposure_by_market={"0x123": 3000.0},
            target_return=0.15,
            correlation=None,
            final_equity=11200.0,
            peak_equity=11500.0,
            total_fees=10.0,
        )

        config = {
            "wallet": "0xwallet",
            "policy": "mirror_latency",
            "start": "2024-01-01",
            "end": "2024-12-31",
            "initial_cash": 10000.0,
        }

        report = generate_markdown_report(metrics, config, run_id="test-123")

        assert "# Backtest Report: test-123" in report
        assert "0xwallet" in report
        assert "12.00%" in report  # Two decimal places
        assert "mirror_latency" in report

    def test_includes_performance_summary(self):
        """Should include performance metrics table."""
        metrics = BacktestMetrics(
            total_return=0.12,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown=0.05,
            max_drawdown_duration=timedelta(0),
            total_trades=10,
            win_rate=0.6,
            avg_trade_return=0.01,
            skipped_trades=2,
            skipped_rate=0.17,
            max_exposure=5000.0,
            avg_exposure=2000.0,
            exposure_by_market={},
            target_return=0.15,
            correlation=None,
            final_equity=11200.0,
            peak_equity=11500.0,
            total_fees=10.0,
        )

        config = {"initial_cash": 10000.0}
        report = generate_markdown_report(metrics, config)

        assert "$10,000.00" in report or "10,000" in report
        assert "$11,200.00" in report or "11,200" in report
        assert "Sharpe" in report

    def test_includes_risk_metrics(self):
        """Should include Sharpe ratio and drawdown."""
        metrics = BacktestMetrics(
            total_return=0.12,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown=0.05,
            max_drawdown_duration=timedelta(0),
            total_trades=10,
            win_rate=0.6,
            avg_trade_return=0.01,
            skipped_trades=2,
            skipped_rate=0.17,
            max_exposure=5000.0,
            avg_exposure=2000.0,
            exposure_by_market={},
            target_return=0.15,
            correlation=None,
            final_equity=11200.0,
            peak_equity=11500.0,
            total_fees=10.0,
        )

        config = {"initial_cash": 10000.0}
        report = generate_markdown_report(metrics, config)

        assert "1.50" in report  # Sharpe ratio
        assert "5.0%" in report or "5.00%" in report  # Drawdown

    def test_generates_unique_run_id(self):
        """Should generate unique run ID if not provided."""
        metrics = BacktestMetrics(
            total_return=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown=0.0,
            max_drawdown_duration=timedelta(0),
            total_trades=0,
            win_rate=0.0,
            avg_trade_return=0.0,
            skipped_trades=0,
            skipped_rate=0.0,
            max_exposure=0.0,
            avg_exposure=0.0,
            exposure_by_market={},
            target_return=0.0,
            correlation=None,
            final_equity=10000.0,
            peak_equity=10000.0,
            total_fees=0.0,
        )

        config = {}
        report1 = generate_markdown_report(metrics, config)
        report2 = generate_markdown_report(metrics, config)

        # Extract run IDs from reports
        run_id_1 = report1.split(": ")[1].split("\n")[0]
        run_id_2 = report2.split(": ")[1].split("\n")[0]

        assert run_id_1 != run_id_2

    def test_handles_missing_target_return(self):
        """Should handle case where target return is not provided."""
        metrics = BacktestMetrics(
            total_return=0.12,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown=0.05,
            max_drawdown_duration=timedelta(0),
            total_trades=10,
            win_rate=0.6,
            avg_trade_return=0.01,
            skipped_trades=2,
            skipped_rate=0.17,
            max_exposure=5000.0,
            avg_exposure=2000.0,
            exposure_by_market={},
            target_return=0.0,  # No target return
            correlation=None,
            final_equity=11200.0,
            peak_equity=11500.0,
            total_fees=10.0,
        )

        config = {}
        report = generate_markdown_report(metrics, config)

        # Should still generate report
        assert "# Backtest Report" in report

    def test_includes_trade_statistics(self):
        """Should include trade count and skip rate."""
        metrics = BacktestMetrics(
            total_return=0.12,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown=0.05,
            max_drawdown_duration=timedelta(0),
            total_trades=10,
            win_rate=0.6,
            avg_trade_return=0.01,
            skipped_trades=2,
            skipped_rate=0.17,
            max_exposure=5000.0,
            avg_exposure=2000.0,
            exposure_by_market={},
            target_return=0.15,
            correlation=None,
            final_equity=11200.0,
            peak_equity=11500.0,
            total_fees=10.0,
        )

        config = {}
        report = generate_markdown_report(metrics, config)

        assert "10" in report  # Total trades
        assert "2" in report   # Skipped trades
        assert "17" in report  # Skip rate percentage


class TestSaveReport:
    """Tests for save_report function."""

    def test_saves_report_to_file(self, tmp_path):
        """Should save report to file system."""
        report = "# Test Report\n\nThis is a test report."

        output_path = save_report(report, run_id="test-run", reports_dir=str(tmp_path))

        # Check file was created
        import os
        assert os.path.exists(output_path)
        assert output_path.endswith("report.md")

        # Check content
        with open(output_path, "r") as f:
            content = f.read()
        assert content == report

    def test_creates_directory_if_needed(self, tmp_path):
        """Should create directory if it doesn't exist."""
        report = "# Test Report"

        nested_path = tmp_path / "nested" / "dir"
        output_path = save_report(report, run_id="test", reports_dir=str(nested_path))

        import os
        assert os.path.exists(output_path)
