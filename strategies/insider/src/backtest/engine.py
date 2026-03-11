"""
Backtest engine for insider trading strategy.

Orchestrates:
- Signal generation
- Price data fetching
- Order execution
- Portfolio management
- Performance tracking
"""
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any
from pathlib import Path
import json

from ..normalize.schema import (
    InsiderSignal, PriceBar, TradeResult
)
from ..data.price_provider import get_price_provider
from .execution import ExecutionModel
from .portfolio import Portfolio

logger = logging.getLogger(__name__)


class BacktestEngine:
    """
    Backtest engine for insider buy signal strategy.
    """

    def __init__(
        self,
        initial_cash: Decimal = Decimal("100000"),
        position_size_pct: Decimal = Decimal("0.10"),
        max_positions: int = 5,
        max_daily_new_positions: int = 3,
        stop_loss_pct: Decimal = Decimal("0.08"),
        take_profit_pct: Decimal = Decimal("0.16"),
        hold_bars: Optional[int] = None,  # If set, use time-based exit
        max_hold_bars: int = 60,
        commission_per_share: Decimal = Decimal("0.005"),
        min_commission: Decimal = Decimal("1.0"),
        slippage_bps: Decimal = Decimal("2"),
        fill_assumption: str = "worst",
        timeframe: str = "1D",
        price_provider: Optional[Any] = None,
        trailing_stop_r: Optional[int] = None,  # Trailing stop at R multiples
    ):
        """
        Initialize backtest engine.

        Args:
            initial_cash: Starting capital
            position_size_pct: Per-trade allocation (default 10%)
            max_positions: Max concurrent positions
            max_daily_new_positions: Max new positions per day
            stop_loss_pct: Stop loss percentage
            take_profit_pct: Take profit percentage
            hold_bars: Optional fixed holding period (time-based exit)
            max_hold_bars: Maximum holding period even with stops
            commission_per_share: Commission per share
            min_commission: Minimum commission per order
            slippage_bps: Slippage in basis points
            fill_assumption: "worst", "best", or "open_first"
            timeframe: Bar timeframe ("1D", "1H", "15m")
            price_provider: Price data provider
            trailing_stop_r: If set, use trailing stops at R multiples (e.g., 2 for 1R/2R)
        """
        self.initial_cash = initial_cash
        self.position_size_pct = position_size_pct
        self.max_positions = max_positions
        self.max_daily_new_positions = max_daily_new_positions
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.hold_bars = hold_bars
        self.max_hold_bars = max_hold_bars
        self.timeframe = timeframe
        self.trailing_stop_r = trailing_stop_r

        # Initialize components
        self.portfolio = Portfolio(
            initial_cash=initial_cash,
            position_size_pct=position_size_pct,
            max_positions=max_positions,
            max_daily_new_positions=max_daily_new_positions,
        )

        self.execution = ExecutionModel(
            commission_per_share=commission_per_share,
            min_commission=min_commission,
            slippage_bps=slippage_bps,
            fill_assumption=fill_assumption,
        )

        self.price_provider = price_provider or get_price_provider("yfinance")

        # Price data cache for backtest
        self.price_cache: Dict[str, List[PriceBar]] = {}

        # Tracking
        self.all_signals: List[InsiderSignal] = []
        self.trades: List[TradeResult] = []
        self.signal_log: List[Dict[str, Any]] = []

    def load_price_data(
        self,
        signals: List[InsiderSignal],
        start_date: date,
        end_date: date,
    ) -> None:
        """
        Load price data for all signal tickers.

        Args:
            signals: List of signals
            start_date: Backtest start date
            end_date: Backtest end date
        """
        tickers = set(s.ticker for s in signals)
        logger.info(f"Loading price data for {len(tickers)} tickers...")

        # Add buffer to start_date for signals that may enter earlier
        buffer_start = start_date - timedelta(days=30)

        for ticker in tickers:
            bars = self.price_provider.fetch_bars(
                ticker=ticker,
                start_date=buffer_start,
                end_date=end_date,
                timeframe=self.timeframe,
            )
            if bars:
                self.price_cache[ticker] = bars
                logger.debug(f"Loaded {len(bars)} bars for {ticker}")
            else:
                logger.warning(f"No price data available for {ticker}")

        logger.info(f"Loaded price data for {len(self.price_cache)} tickers")

    def get_bar_for_date(self, ticker: str, target_date: date) -> Optional[PriceBar]:
        """Get the price bar for a specific date."""
        bars = self.price_cache.get(ticker, [])
        for bar in bars:
            if bar.datetime.date() == target_date:
                return bar
        return None

    def get_next_bar_after(self, ticker: str, target_date: date) -> Optional[PriceBar]:
        """Get the first bar strictly after the target date."""
        bars = self.price_cache.get(ticker, [])
        for bar in bars:
            if bar.datetime.date() > target_date:
                return bar
        return None

    def run(
        self,
        signals: List[InsiderSignal],
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """
        Run the backtest.

        Args:
            signals: List of trading signals
            start_date: Backtest start date
            end_date: Backtest end date

        Returns:
            Dictionary with backtest results
        """
        self.all_signals = signals

        # Load price data
        self.load_price_data(signals, start_date, end_date)

        # Filter signals to date range
        active_signals = [
            s for s in signals
            if start_date <= s.signal_date <= end_date
        ]
        logger.info(f"Running backtest with {len(active_signals)} active signals from {start_date} to {end_date}")

        # Group signals by date for efficient processing
        signals_by_date: Dict[date, List[InsiderSignal]] = defaultdict(list)
        for signal in active_signals:
            signals_by_date[signal.signal_date].append(signal)

        # Get all unique dates from price data
        all_dates = set()
        for bars in self.price_cache.values():
            for bar in bars:
                all_dates.add(bar.datetime.date())

        sorted_dates = sorted(d for d in all_dates if start_date <= d <= end_date)

        # Run day by day
        current_bar_index = 0

        for current_date in sorted_dates:
            # Reset daily counters
            self.portfolio.reset_daily_counters()

            # Get current prices for all positions
            current_prices = {}
            for ticker in list(self.portfolio.positions.keys()):
                bar = self.get_bar_for_date(ticker, current_date)
                if bar:
                    current_prices[ticker] = bar.close
                else:
                    # Missing data - use last known
                    current_prices[ticker] = self.portfolio.positions[ticker].entry_price

            # Process exits first
            self._process_exits(current_date, current_bar_index, current_prices)

            # Process new entries
            for signal in signals_by_date.get(current_date, []):
                self._process_entry(signal, current_date, current_bar_index)

            # Create snapshot
            self.portfolio.create_snapshot(current_date, current_prices)

            current_bar_index += 1

        # Force close remaining positions at end
        if self.portfolio.positions:
            logger.info(f"Force closing {len(self.portfolio.positions)} remaining positions")
            # Get last available prices
            final_prices = {}
            for ticker, position in self.portfolio.positions.items():
                bars = self.price_cache.get(ticker, [])
                if bars:
                    final_prices[ticker] = bars[-1].close
                else:
                    final_prices[ticker] = position.entry_price

            self.portfolio.force_close_all(
                exit_date=end_date,
                prices=final_prices,
                costs_per_share=self.execution.commission_per_share,
                current_bar_index=current_bar_index,
            )

        self.trades = self.portfolio.closed_trades

        # Compile results
        results = self._compile_results(start_date, end_date)
        return results

    def _process_entry(
        self,
        signal: InsiderSignal,
        current_date: date,
        bar_index: int,
    ) -> None:
        """Process a signal entry."""
        # Check if we can open position
        can_open, reason = self.portfolio.can_open_position(signal.ticker, current_date)
        if not can_open:
            self._log_signal(signal, "skipped", reason)
            return

        # Get entry bar (next day's open)
        entry_bar = self.get_next_bar_after(signal.ticker, signal.signal_date)
        if not entry_bar:
            self._log_signal(signal, "skipped", "no_entry_bar")
            return

        entry_price = entry_bar.open

        # Calculate position size
        shares = self.portfolio.calculate_position_size(entry_price, current_date)
        if shares is None:
            self._log_signal(signal, "skipped", "insufficient_cash")
            return

        # Calculate stop and take prices
        stop_loss = entry_price * (Decimal("1") - self.stop_loss_pct)
        take_profit = entry_price * (Decimal("1") + self.take_profit_pct)

        # Open position
        success = self.portfolio.open_position(
            ticker=signal.ticker,
            entry_date=current_date,
            entry_price=entry_price,
            shares=shares,
            entry_bar_index=bar_index,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        if success:
            self._log_signal(signal, "entered", f"@ ${entry_price:.2f}")
        else:
            self._log_signal(signal, "skipped", "open_failed")

    def _process_exits(
        self,
        current_date: date,
        bar_index: int,
        current_prices: Dict[str, Decimal],
    ) -> None:
        """Process exits for open positions."""
        tickers_to_close = []

        for ticker, position in list(self.portfolio.positions.items()):
            bar = self.get_bar_for_date(ticker, current_date)
            if not bar:
                continue

            # Calculate hold time
            hold_bars = bar_index - position.entry_bar_index

            # Check if max hold exceeded
            if hold_bars >= self.max_hold_bars:
                tickers_to_close.append((ticker, bar.close, "max_hold"))
                continue

            # Check time-based exit
            if self.hold_bars is not None and hold_bars >= self.hold_bars:
                tickers_to_close.append((ticker, bar.close, "time_exit"))
                continue

            # Check bracket exits (with trailing stop support)
            fill, exit_reason, new_highest = self.execution.check_bracket_exit(
                bar=bar,
                entry_price=position.entry_price,
                shares=position.shares,
                stop_loss_pct=self.stop_loss_pct,
                take_profit_pct=self.take_profit_pct,
                timestamp=datetime.combine(current_date, datetime.min.time()),
                trailing_stop_r=self.trailing_stop_r,
                highest_price=position.highest_price,
            )

            # Update highest price in position
            if new_highest is not None:
                position.highest_price = new_highest

            if fill:
                fill.ticker = ticker
                # Close position
                self.portfolio.close_position(
                    ticker=ticker,
                    exit_date=current_date,
                    exit_price=fill.price,
                    exit_reason=exit_reason,
                    costs=fill.commission,
                    current_bar_index=bar_index,
                )
            else:
                # Position remains open
                pass

        # Close positions flagged for exit
        for ticker, exit_price, reason in tickers_to_close:
            if ticker in self.portfolio.positions:
                position = self.portfolio.positions[ticker]
                costs = self.execution.calculate_commission(position.shares)
                self.portfolio.close_position(
                    ticker=ticker,
                    exit_date=current_date,
                    exit_price=exit_price,
                    exit_reason=reason,
                    costs=costs,
                    current_bar_index=bar_index,
                )

    def _log_signal(
        self,
        signal: InsiderSignal,
        status: str,
        detail: str = "",
    ) -> None:
        """Log signal processing."""
        log_entry = {
            "ticker": signal.ticker,
            "signal_date": signal.signal_date.isoformat(),
            "buy_value_usd": str(signal.buy_value_usd),
            "status": status,
            "detail": detail,
        }
        self.signal_log.append(log_entry)
        logger.debug(f"Signal {signal.ticker} {signal.signal_date}: {status} - {detail}")

    def _compile_results(
        self,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """Compile backtest results."""
        trades = self.trades
        snapshots = self.portfolio.snapshots

        if not snapshots:
            logger.warning("No snapshots generated - check data")
            return {}

        initial_equity = self.initial_cash
        final_equity = snapshots[-1].equity if snapshots else initial_equity
        total_return = (final_equity - initial_equity) / initial_equity

        # Calculate CAGR
        days = (end_date - start_date).days
        years = days / 365.25
        if years > 0:
            cagr = Decimal(float(final_equity / initial_equity) ** (1 / years) - 1)
        else:
            cagr = Decimal("0")

        # Calculate max drawdown
        max_drawdown = max((s.drawdown for s in snapshots), default=Decimal("0"))

        # Trade statistics
        n_trades = len(trades)
        winning_trades = [t for t in trades if t.is_win]
        losing_trades = [t for t in trades if not t.is_win]

        win_rate = len(winning_trades) / n_trades if n_trades > 0 else Decimal("0")

        avg_win = sum(t.net_pnl for t in winning_trades) / len(winning_trades) if winning_trades else Decimal("0")
        avg_loss = sum(t.net_pnl for t in losing_trades) / len(losing_trades) if losing_trades else Decimal("0")

        gross_profit = sum(t.gross_pnl for t in winning_trades)
        gross_loss = abs(sum(t.gross_pnl for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else Decimal("0")

        # Average hold time
        avg_hold_bars = sum(t.hold_bars for t in trades) / n_trades if n_trades > 0 else Decimal("0")

        # Sharpe ratio (simplified - daily returns)
        if len(snapshots) > 1:
            returns = []
            for i in range(1, len(snapshots)):
                prev_eq = snapshots[i - 1].equity
                curr_eq = snapshots[i].equity
                if prev_eq > 0:
                    returns.append(float((curr_eq - prev_eq) / prev_eq))

            import statistics
            if returns:
                avg_return = statistics.mean(returns)
                std_return = statistics.stdev(returns) if len(returns) > 1 else 0.001
                sharpe = (avg_return * 252) / (std_return * (252 ** 0.5)) if std_return > 0 else 0
            else:
                sharpe = 0
        else:
            sharpe = 0

        # Exposure and turnover
        avg_positions = sum(s.n_positions for s in snapshots) / len(snapshots) if snapshots else 0
        exposure = avg_positions / self.max_positions if self.max_positions > 0 else 0

        results = {
            "summary": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "initial_equity": str(initial_equity),
                "final_equity": str(final_equity),
                "total_return": str(total_return),
                "cagr": str(cagr),
                "max_drawdown": str(max_drawdown),
                "sharpe_ratio": sharpe,
            },
            "trades": {
                "n_trades": n_trades,
                "win_rate": str(win_rate),
                "avg_win": str(avg_win),
                "avg_loss": str(avg_loss),
                "profit_factor": str(profit_factor),
                "avg_hold_bars": str(avg_hold_bars),
            },
            "portfolio": {
                "exposure": str(exposure),
                "avg_positions": avg_positions,
            },
            "equity_curve": [(s.date.isoformat(), str(s.equity)) for s in snapshots],
            "signal_log": self.signal_log,
        }

        return results

    def save_results(self, results: Dict[str, Any], output_path: str) -> None:
        """Save backtest results to JSON file."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"Results saved to {output_path}")
