"""Tests for criteria evaluation."""

import pytest
from src.screener.models import CriterionConfig, CriterionType, Operator
from src.screener.criteria import CriteriaEvaluator


def test_pe_ratio_filter():
    """Test P/E ratio filtering."""
    criteria = [
        CriterionConfig(
            type=CriterionType.FUNDAMENTAL,
            metric="pe_ratio",
            operator=Operator.LT,
            value=30.0
        )
    ]
    evaluator = CriteriaEvaluator(criteria)

    # Mock fundamental data
    class MockFund:
        def __init__(self, pe):
            self.pe_ratio = pe

    # Should pass
    passed, failures = evaluator.evaluate("TEST", None, MockFund(25.0))
    assert passed is True
    assert len(failures) == 0

    # Should fail
    passed, failures = evaluator.evaluate("TEST", None, MockFund(35.0))
    assert passed is False
    assert "pe_ratio < 30.0" in failures[0]


def test_rsi_filter():
    """Test RSI technical filter."""
    criteria = [
        CriterionConfig(
            type=CriterionType.TECHNICAL,
            metric="rsi_14",
            operator=Operator.LT,
            value=70.0
        )
    ]
    evaluator = CriteriaEvaluator(criteria)

    # Mock price data
    class MockPrice:
        def __init__(self, rsi):
            self.rsi_14 = rsi
            self.price = 100
            self.ma50 = None
            self.ma200 = None

    # Should pass
    passed, _ = evaluator.evaluate("TEST", MockPrice(50), None)
    assert passed is True

    # Should fail
    passed, _ = evaluator.evaluate("TEST", MockPrice(80), None)
    assert passed is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
