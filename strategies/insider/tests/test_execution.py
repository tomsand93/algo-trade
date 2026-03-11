"""
Unit tests for execution model and portfolio logic.
"""
import pytest
from datetime import date, datetime
from decimal import Decimal

from src.normalize.schema import PriceBar, Position, TradeResult, Fill
from src.backtest.execution import ExecutionModel
from src.backtest.portfolio import Portfolio


class TestExecutionModel:
    """Test execution model with slippage and commission."""

    def test_calculate_commission(self):
        exec_model = ExecutionModel(
            commission_per_share=Decimal("0.005"),
            min_commission=Decimal("1.0"),
        )

        # Normal trade
        comm = exec_model.calculate_commission(Decimal("1000"))
        assert comm == Decimal("5.0")

        # Minimum commission
        comm = exec_model.calculate_commission(Decimal("100"))
        assert comm == Decimal("1.0")

    def test_fill_at_open(self):
        exec_model = ExecutionModel(
            commission_per_share=Decimal("0.005"),
            min_commission=Decimal("1.0"),
            slippage_bps=Decimal("2"),
        )

        bar = PriceBar(
            datetime=datetime(2024, 1, 15, 9, 30),
            open=Decimal("100.00"),
            high=Decimal("101.00"),
            low=Decimal("99.00"),
            close=Decimal("100.50"),
            volume=1000000,
        )

        fill = exec_model.fill_at_open(
            bar=bar,
            side="buy",
            shares=Decimal("100"),
            timestamp=datetime(2024, 1, 15, 9, 30),
        )

        # Price should include slippage (worsened for buy)
        assert fill.price > Decimal("100.00")
        assert fill.price < Decimal("100.05")  # 2 bps on $100 = $0.02
        assert fill.shares == Decimal("100")
        assert fill.side == "buy"

    def test_stop_loss_hit(self):
        exec_model = ExecutionModel(
            commission_per_share=Decimal("0.005"),
            min_commission=Decimal("1.0"),
            slippage_bps=Decimal("2"),
        )

        bar = PriceBar(
            datetime=datetime(2024, 1, 16, 9, 30),
            open=Decimal("95.00"),
            high=Decimal("96.00"),
            low=Decimal("94.00"),
            close=Decimal("95.50"),
            volume=1000000,
        )

        stop_price = Decimal("96.00")  # Stop at $96

        fill = exec_model.fill_at_stop(
            bar=bar,
            stop_price=stop_price,
            shares=Decimal("100"),
            timestamp=datetime(2024, 1, 16, 10, 0),
        )

        assert fill is not None  # Stop hit (bar low <= stop)
        assert fill.side == "sell"

    def test_stop_loss_not_hit(self):
        exec_model = ExecutionModel(
            commission_per_share=Decimal("0.005"),
            min_commission=Decimal("1.0"),
        )

        bar = PriceBar(
            datetime=datetime(2024, 1, 16, 9, 30),
            open=Decimal("97.00"),
            high=Decimal("98.00"),
            low=Decimal("96.50"),
            close=Decimal("97.50"),
            volume=1000000,
        )

        stop_price = Decimal("96.00")

        fill = exec_model.fill_at_stop(
            bar=bar,
            stop_price=stop_price,
            shares=Decimal("100"),
            timestamp=datetime(2024, 1, 16, 10, 0),
        )

        assert fill is None  # Stop not hit

    def test_take_profit_hit(self):
        exec_model = ExecutionModel(
            commission_per_share=Decimal("0.005"),
            min_commission=Decimal("1.0"),
        )

        bar = PriceBar(
            datetime=datetime(2024, 1, 16, 9, 30),
            open=Decimal("110.00"),
            high=Decimal("112.00"),
            low=Decimal("109.00"),
            close=Decimal("111.00"),
            volume=1000000,
        )

        take_price = Decimal("110.00")

        fill = exec_model.fill_at_take(
            bar=bar,
            take_price=take_price,
            shares=Decimal("100"),
            timestamp=datetime(2024, 1, 16, 10, 0),
        )

        assert fill is not None  # Take hit (bar high >= take)
        assert fill.side == "sell"

    def test_bracket_exit_stop(self):
        exec_model = ExecutionModel(
            fill_assumption="worst",
        )

        bar = PriceBar(
            datetime=datetime(2024, 1, 16, 9, 30),
            open=Decimal("100.00"),
            high=Decimal("108.00"),
            low=Decimal("91.00"),
            close=Decimal("95.00"),
            volume=1000000,
        )

        entry_price = Decimal("100.00")
        shares = Decimal("100")

        # 8% stop = $92, 16% take = $116
        fill, reason, new_highest = exec_model.check_bracket_exit(
            bar=bar,
            entry_price=entry_price,
            shares=shares,
            stop_loss_pct=Decimal("0.08"),
            take_profit_pct=Decimal("0.16"),
            timestamp=datetime(2024, 1, 16, 10, 0),
        )

        # Both hit (92 <= 92 stop, 108 < 116 take not hit)
        # Actually only stop is hit here
        assert fill is not None
        assert reason == "stop_loss"
        assert new_highest == Decimal("108.00")

    def test_bracket_both_hit_worst(self):
        exec_model = ExecutionModel(
            fill_assumption="worst",
        )

        bar = PriceBar(
            datetime=datetime(2024, 1, 16, 9, 30),
            open=Decimal("100.00"),
            high=Decimal("120.00"),  # Above take
            low=Decimal("90.00"),   # Below stop
            close=Decimal("110.00"),
            volume=1000000,
        )

        entry_price = Decimal("100.00")
        shares = Decimal("100")

        fill, reason, new_highest = exec_model.check_bracket_exit(
            bar=bar,
            entry_price=entry_price,
            shares=shares,
            stop_loss_pct=Decimal("0.08"),
            take_profit_pct=Decimal("0.16"),
            timestamp=datetime(2024, 1, 16, 10, 0),
        )

        assert fill is not None
        assert reason == "both_stop"  # Worst assumption
        assert new_highest == Decimal("120.00")


class TestPortfolio:
    """Test portfolio management."""

    def test_initial_state(self):
        portfolio = Portfolio(
            initial_cash=Decimal("100000"),
            position_size_pct=Decimal("0.10"),
            max_positions=5,
        )

        assert portfolio.cash == Decimal("100000")
        assert portfolio.n_positions == 0

    def test_can_open_position(self):
        portfolio = Portfolio(
            initial_cash=Decimal("100000"),
            position_size_pct=Decimal("0.10"),
            max_positions=5,
        )

        can_open, reason = portfolio.can_open_position("AAPL", date.today())
        assert can_open is True
        assert reason == ""

    def test_cannot_open_already_holding(self):
        portfolio = Portfolio(
            initial_cash=Decimal("100000"),
            position_size_pct=Decimal("0.10"),
            max_positions=5,
        )

        # Open position
        portfolio.open_position(
            ticker="AAPL",
            entry_date=date.today(),
            entry_price=Decimal("100"),
            shares=Decimal("100"),
            entry_bar_index=0,
        )

        can_open, reason = portfolio.can_open_position("AAPL", date.today())
        assert can_open is False
        assert reason == "already_holding"

    def test_calculate_position_size(self):
        portfolio = Portfolio(
            initial_cash=Decimal("100000"),
            position_size_pct=Decimal("0.10"),
            max_positions=5,
        )

        price = Decimal("100")
        shares = portfolio.calculate_position_size(price, date.today())

        # 10% of $100,000 = $10,000 / $100 = 100 shares
        assert shares == Decimal("100")

    def test_open_position(self):
        portfolio = Portfolio(
            initial_cash=Decimal("100000"),
            position_size_pct=Decimal("0.10"),
            max_positions=5,
        )

        success = portfolio.open_position(
            ticker="AAPL",
            entry_date=date(2024, 1, 15),
            entry_price=Decimal("100"),
            shares=Decimal("100"),
            entry_bar_index=0,
        )

        assert success is True
        assert portfolio.cash == Decimal("90000")  # 100000 - 10000
        assert portfolio.n_positions == 1

    def test_close_position(self):
        portfolio = Portfolio(
            initial_cash=Decimal("100000"),
            position_size_pct=Decimal("0.10"),
            max_positions=5,
        )

        portfolio.open_position(
            ticker="AAPL",
            entry_date=date(2024, 1, 15),
            entry_price=Decimal("100"),
            shares=Decimal("100"),
            entry_bar_index=0,
        )

        result = portfolio.close_position(
            ticker="AAPL",
            exit_date=date(2024, 1, 20),
            exit_price=Decimal("110"),
            exit_reason="take_profit",
            costs=Decimal("10"),
            current_bar_index=5,
        )

        assert result is not None
        assert result.net_pnl == Decimal("990")  # (110-100)*100 - 10
        assert portfolio.cash == Decimal("100990")  # 90000 + 11000 - 10
        assert portfolio.n_positions == 0

    def test_max_positions_limit(self):
        portfolio = Portfolio(
            initial_cash=Decimal("100000"),
            position_size_pct=Decimal("0.10"),
            max_positions=3,
        )

        # Open 3 positions
        for i in range(3):
            portfolio.open_position(
                ticker=f"STOCK{i}",
                entry_date=date.today(),
                entry_price=Decimal("100"),
                shares=Decimal("10"),  # Small size
                entry_bar_index=0,
            )

        can_open, reason = portfolio.can_open_position("NEW", date.today())
        assert can_open is False
        assert reason == "max_positions"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
