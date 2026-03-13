"""
FVG Breakout Strategy - Backtesting Engine
===========================================
Simulates trades with strict rule enforcement.
No lookahead bias, no survival bias, no discretion.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
import pandas as pd
import numpy as np

from src.pattern_detection import PatternDetector, TradeSetup
from src.config import StrategyConfig


@dataclass
class TradeRecord:
    """Individual trade record"""
    date: str
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    entry_time: str
    exit_price: float
    exit_time: str
    exit_reason: str  # "STOP_LOSS", "TAKE_PROFIT", "EOD"
    pnl: float
    pnl_pct: float
    r_multiple: float
    bars_held: int
    outcome: str  # "WIN" or "LOSS"


@dataclass
class BacktestResult:
    """Complete backtest results"""
    trades: List[TradeRecord] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    dates: List[str] = field(default_factory=list)
    initial_capital: float = 100000.0  # Add initial capital

    # Metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    avg_r_multiple: float = 0.0
    expectancy: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0


class BacktestEngine:
    """
    Backtesting engine with strict rule enforcement.

    Rules Enforced:
    - Maximum 1 trade per symbol per day
    - No trades before 09:35 ET
    - No partial entries or averaging
    - Fixed stop loss and take profit
    - No early exits
    """

    def __init__(self, initial_capital: float = 100000.0, long_only: bool = False, config: StrategyConfig = None):
        self.initial_capital = initial_capital
        self.long_only = long_only
        self.config = config or StrategyConfig()
        self.detector = PatternDetector(risk_reward_ratio=3.0, long_only=long_only, config=self.config)

        # Track daily trades to enforce limit
        self.daily_trades: Dict[str, set] = {}  # {date: set of symbols traded}

    def _can_trade(self, trade_date: str, symbol: str) -> bool:
        """
        Check if trade is allowed (max 1 per symbol per day).
        """
        if trade_date not in self.daily_trades:
            self.daily_trades[trade_date] = set()

        return symbol not in self.daily_trades[trade_date]

    def _record_trade_attempt(self, trade_date: str, symbol: str) -> None:
        """Record that a symbol was traded on this date."""
        if trade_date not in self.daily_trades:
            self.daily_trades[trade_date] = set()
        self.daily_trades[trade_date].add(symbol)

    def simulate_trade(
        self,
        df_1m: pd.DataFrame,
        setup: TradeSetup,
        symbol: str
    ) -> Optional[TradeRecord]:
        """
        Simulate a single trade from entry to exit.
        Includes break-even rule: move SL to entry_price when +1R is reached.

        Edge cases (per spec):
        - BE trigger uses intrabar high/low (not close)
        - If same candle hits both BE trigger and original SL, assume SL hit first
        - SL always checked before TP (conservative)
        - After BE triggers, SL = entry_price exactly (no buffer)

        Args:
            df_1m: 1-minute DataFrame
            setup: TradeSetup object
            symbol: Symbol name

        Returns:
            TradeRecord if trade completes, None otherwise
        """
        entry_idx = df_1m.index.get_indexer([setup.entry_time], method='nearest')[0]

        if entry_idx == -1:
            return None

        entry_price = setup.entry_price
        stop_loss = setup.stop_loss
        take_profit = setup.take_profit
        original_sl = stop_loss

        # Break-even state
        be_triggered = False
        if setup.direction == "long":
            r_value = entry_price - stop_loss
            be_trigger_price = entry_price + r_value   # +1R
        else:
            r_value = stop_loss - entry_price
            be_trigger_price = entry_price - r_value   # -1R

        exit_price = None
        exit_time = None
        exit_reason = None

        # Simulate trade forward bar-by-bar
        for i in range(entry_idx + 1, len(df_1m)):
            bar = df_1m.iloc[i]

            # Earlier EOD exit if configured
            if self.config.eod_exit_time is not None:
                bar_time = bar.name.time() if hasattr(bar.name, 'time') else bar.name
                if bar_time >= self.config.eod_exit_time:
                    exit_price = bar["close"]
                    exit_time = bar.name
                    exit_reason = "EOD"
                    break

            if setup.direction == "long":
                # Edge case: same candle hits BE trigger AND original SL → worst case SL first
                if not be_triggered and bar["high"] >= be_trigger_price and bar["low"] <= original_sl:
                    exit_price = original_sl
                    exit_time = bar.name
                    exit_reason = "STOP_LOSS"
                    break

                # Check BE trigger (uses intrabar high per spec)
                if not be_triggered and bar["high"] >= be_trigger_price:
                    be_triggered = True
                    stop_loss = entry_price  # Move SL to break-even

                # Check SL first (conservative)
                if bar["low"] <= stop_loss:
                    exit_price = stop_loss
                    exit_time = bar.name
                    exit_reason = "BREAK_EVEN" if be_triggered else "STOP_LOSS"
                    break

                # Check TP
                if bar["high"] >= take_profit:
                    exit_price = take_profit
                    exit_time = bar.name
                    exit_reason = "TAKE_PROFIT"
                    break

            else:  # short
                # Edge case: same candle hits BE trigger AND original SL → worst case SL first
                if not be_triggered and bar["low"] <= be_trigger_price and bar["high"] >= original_sl:
                    exit_price = original_sl
                    exit_time = bar.name
                    exit_reason = "STOP_LOSS"
                    break

                # Check BE trigger (uses intrabar low per spec)
                if not be_triggered and bar["low"] <= be_trigger_price:
                    be_triggered = True
                    stop_loss = entry_price  # Move SL to break-even

                # Check SL first (conservative)
                if bar["high"] >= stop_loss:
                    exit_price = stop_loss
                    exit_time = bar.name
                    exit_reason = "BREAK_EVEN" if be_triggered else "STOP_LOSS"
                    break

                # Check TP
                if bar["low"] <= take_profit:
                    exit_price = take_profit
                    exit_time = bar.name
                    exit_reason = "TAKE_PROFIT"
                    break

        # End of day exit if no SL/TP hit
        if exit_price is None:
            exit_price = df_1m.iloc[-1]["close"]
            exit_time = df_1m.iloc[-1].name
            exit_reason = "EOD"

        # Calculate PnL
        if setup.direction == "long":
            pnl = exit_price - entry_price
        else:
            pnl = entry_price - exit_price

        pnl_pct = (pnl / entry_price) * 100

        # R multiple uses original SL (the true risk taken)
        risk = abs(entry_price - original_sl)
        r_multiple = pnl / risk if risk > 0 else 0

        # Determine outcome
        outcome = "WIN" if pnl > 0 else "LOSS"

        bars_held = (pd.Timestamp(exit_time) - pd.Timestamp(setup.entry_time)).total_seconds() / 60

        return TradeRecord(
            date=setup.date,
            symbol=symbol,
            direction=setup.direction,
            entry_price=entry_price,
            stop_loss=original_sl,
            take_profit=take_profit,
            entry_time=str(setup.entry_time),
            exit_price=exit_price,
            exit_time=str(exit_time),
            exit_reason=exit_reason,
            pnl=pnl,
            pnl_pct=pnl_pct,
            r_multiple=r_multiple,
            bars_held=int(bars_held),
            outcome=outcome
        )

    def run_backtest(
        self,
        data: Dict[str, Dict[str, pd.DataFrame]],
        progress_callback=None
    ) -> BacktestResult:
        """
        Run full backtest across all symbols and dates.

        Args:
            data: {symbol: {"5Min": df_5m, "1Min": df_1m}}
            progress_callback: Optional callback for progress updates

        Returns:
            BacktestResult with all trades and metrics
        """
        result = BacktestResult()
        result.initial_capital = self.initial_capital
        current_equity = self.initial_capital
        result.equity_curve.append(current_equity)

        # Sort symbols for consistent processing
        symbols = sorted(data.keys())

        for symbol_idx, symbol in enumerate(symbols):
            if progress_callback:
                progress_callback(symbol_idx, len(symbols), symbol)

            symbol_data = data[symbol]
            df_5m = symbol_data["5Min"]
            df_1m = symbol_data["1Min"]

            # Get unique trading days
            df_5m_filtered = df_5m.between_time("09:30", "16:00")
            unique_days = df_5m_filtered.index.normalize().unique()

            for day in unique_days:
                day_str = day.strftime("%Y-%m-%d")

                # Get data for this day
                day_5m = df_5m.loc[day_str]
                day_1m = df_1m.loc[day_str]

                # Check if already traded this symbol today
                if not self._can_trade(day_str, symbol):
                    continue

                # Get daily setup (09:30-09:35)
                daily_setup = self.detector.get_daily_setup(day_5m, day_str, symbol)

                if daily_setup is None or not daily_setup.valid:
                    continue

                # Find trade setup
                setup = self.detector.find_trade_setup(day_1m, daily_setup)

                if setup is None:
                    continue

                # Simulate the trade
                trade = self.simulate_trade(day_1m, setup, symbol)

                if trade is not None:
                    # Record the trade attempt
                    self._record_trade_attempt(day_str, symbol)

                    # Add to results
                    result.trades.append(trade)
                    result.dates.append(trade.exit_time)

                    # Update equity
                    current_equity += trade.pnl
                    result.equity_curve.append(current_equity)

        # Calculate metrics
        self._calculate_metrics(result)

        return result

    def _calculate_metrics(self, result: BacktestResult) -> None:
        """Calculate performance metrics from trades."""
        if not result.trades:
            return

        result.total_trades = len(result.trades)
        result.winning_trades = sum(1 for t in result.trades if t.outcome == "WIN")
        result.losing_trades = sum(1 for t in result.trades if t.outcome == "LOSS")

        result.win_rate = (result.winning_trades / result.total_trades * 100) if result.total_trades > 0 else 0

        # PnL metrics
        result.total_pnl = sum(t.pnl for t in result.trades)
        result.total_pnl_pct = (result.total_pnl / self.initial_capital * 100)

        wins = [t.pnl for t in result.trades if t.outcome == "WIN"]
        losses = [t.pnl for t in result.trades if t.outcome == "LOSS"]

        result.avg_win = np.mean(wins) if wins else 0
        result.avg_loss = np.mean(losses) if losses else 0
        result.largest_win = max(wins) if wins else 0
        result.largest_loss = min(losses) if losses else 0

        # R multiple metrics
        r_multiples = [t.r_multiple for t in result.trades]
        result.avg_r_multiple = np.mean(r_multiples) if r_multiples else 0

        # Expectancy: (Win% * Avg Win) + (Loss% * Avg Loss)
        win_pct = result.winning_trades / result.total_trades if result.total_trades > 0 else 0
        loss_pct = result.losing_trades / result.total_trades if result.total_trades > 0 else 0
        result.expectancy = (win_pct * result.avg_win) + (loss_pct * result.avg_loss)

        # Drawdown calculation
        equity = np.array(result.equity_curve)
        running_max = np.maximum.accumulate(equity)
        drawdown = equity - running_max
        result.max_drawdown = min(drawdown)
        result.max_drawdown_pct = (result.max_drawdown / self.initial_capital * 100)

        # Sharpe Ratio (simplified, assuming 252 trading days)
        if len(result.equity_curve) > 1:
            returns = np.diff(result.equity_curve) / result.equity_curve[:-1]
            result.sharpe_ratio = (np.mean(returns) / np.std(returns) * np.sqrt(252)) if np.std(returns) > 0 else 0
        else:
            result.sharpe_ratio = 0
