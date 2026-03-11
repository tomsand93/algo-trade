"""Event-driven backtester with strict timestamp ordering."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from .config import Config
from .data_loader import load_orderbook, load_trades, merge_events, infer_trade_side
from .events import BookSnapshot, Event, Trade
from .execution import ExecutionModel, Fill
from .strategy import OrderbookStrategy, Signal


@dataclass
class BacktestState:
    """Backtest execution state."""
    current_time: datetime | None = None
    current_book: BookSnapshot | None = None
    next_trade_price: float | None = None
    cash: float = 100000.0
    position_qty: float = 0.0
    position_price: float = 0.0
    equity: float = 100000.0
    equity_curve: list = field(default_factory=list)
    all_trades: list = field(default_factory=list)


class Backtester:
    """Event-driven backtester with no lookahead bias."""

    def __init__(self, config: Config):
        self.config = config
        self.strategy = OrderbookStrategy(config)
        self.execution = ExecutionModel(
            tick_size=config.tick_size,
            slippage_ticks=config.slippage_ticks,
            fee_per_contract=config.fee_per_share_or_contract,
            latency_ms=config.latency_ms,
        )
        self.state = BacktestState(cash=100000.0)

        # Book state for execution
        self._best_bid: float | None = None
        self._best_ask: float | None = None

    def run(
        self,
        trades_path: Path,
        book_path: Path,
    ) -> dict:
        """Run backtest on provided data.

        Args:
            trades_path: Path to trades CSV
            book_path: Path to orderbook CSV

        Returns:
            Dictionary with equity curve, trades, and metrics
        """
        # Load data
        trades = load_trades(trades_path)
        snapshots = load_orderbook(book_path)

        # Merge into event stream (enforces monotonic ordering)
        events = list(merge_events(trades, snapshots))

        # Process events
        for event in events:
            self._process_event(event)

        # Close any pending signals at end
        while self.execution.has_pending():
            sig_info = self.execution.pending_signals[0]
            signal = sig_info["signal"]
            # Force execute at last known price
            if self._best_bid and self._best_ask:
                fill = Fill(
                    timestamp=self.state.current_time or datetime.now(),
                    price=(self._best_bid + self._best_ask) / 2,
                    quantity=signal.quantity,
                    side=signal.direction,
                    fee=0.0,
                    slippage=0.0,
                )
                self._on_fill(fill, signal)

        # Sync trades from strategy for metrics
        self.state.all_trades = [
            {
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "side": t.side,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "pnl": t.pnl,
                "fees": t.fees,
                "slippage": t.slippage,
                "reason": t.reason,
                "p_up": t.p_up,
                "p_down": t.p_down,
                "state_key": t.state_key,
                "dist_samples": t.dist_samples,
            }
            for t in self.strategy.trades
        ]

        # Compute final metrics
        equity_df = pd.DataFrame(
            self.state.equity_curve, columns=["timestamp", "equity"]
        )
        equity_df.set_index("timestamp", inplace=True)

        trades_df = pd.DataFrame(self.state.all_trades)

        return {
            "equity": equity_df,
            "trades": trades_df,
            "metrics": self._compute_metrics(equity_df, trades_df),
        }

    def _process_event(self, event: Event) -> None:
        """Process a single event in timestamp order."""
        # Update time
        if isinstance(event, Trade):
            self.state.current_time = event.timestamp
            self.state.next_trade_price = event.price
        elif isinstance(event, BookSnapshot):
            self.state.current_time = event.timestamp
            self.state.current_book = event
            self._best_bid = event.best_bid
            self._best_ask = event.best_ask
            # Reset next trade price (will be set by next trade event)
            # self.state.next_trade_price = None

        # Get current mid
        current_mid = None
        if self._best_bid and self._best_ask:
            current_mid = (self._best_bid + self._best_ask) / 2

        # Try to execute pending signals
        fill = self.execution.try_execute(
            self.state.current_time,
            self._best_bid,
            self._best_ask,
            self.state.next_trade_price,
        )

        if fill:
            self._on_fill(fill, None)  # Signal already stored in execution
        elif self.execution.has_pending():
            print(f"  [DEBUG] Pending signals: {len(self.execution.pending_signals)}, current_time: {self.state.current_time}")

        # Run strategy on event
        if current_mid is not None:
            signal = self.strategy.on_event(
                event, self.state.current_time, current_mid
            )

            if signal:
                self._on_signal(signal)

        # Update equity
        self._update_equity(current_mid)

    def _on_signal(self, signal: Signal) -> None:
        """Handle strategy signal."""
        # Log signal
        if self.config.log_signals:
            print(
                f"{signal.timestamp} | SIGNAL: {signal.direction.upper()} "
                f"{signal.quantity:.2f} @ {signal.entry_price:.2f} | "
                f"P_up={signal.p_up:.3f} P_down={signal.p_down:.3f} | "
                f"Reason: {signal.reason}"
            )

        # Submit to execution
        execute_time = self.execution.submit_signal(signal, signal.timestamp)
        print(f"  -> Signal submitted, will execute at {execute_time}")

        # Notify strategy of signal acceptance
        self.strategy.on_signal(signal)

    def _on_fill(self, fill: Fill, signal: Signal | None) -> None:
        """Handle order fill."""
        # Update position and cash
        if fill.side in ("long", "buy"):
            # Check if we're closing a short position
            if self.state.position_qty < 0:
                # Closing short: PnL = entry - exit (we want exit < entry)
                closing_qty = min(fill.quantity, abs(self.state.position_qty))
                pnl = (self.state.position_price - fill.price) * closing_qty
                self.state.position_qty += closing_qty  # Moves toward 0
                self.state.cash -= fill.price * closing_qty + fill.fee - pnl
                fill.quantity -= closing_qty  # Any remaining goes to new position

                # If remaining quantity, open long
                if fill.quantity > 0 and self.state.position_qty == 0:
                    self.state.position_qty = fill.quantity
                    self.state.position_price = fill.price
                    self.state.cash -= fill.price * fill.quantity + fill.fee
            elif self.state.position_qty >= 0:
                # Adding to long or opening new long
                self.state.position_qty += fill.quantity
                if self.state.position_qty > 0:
                    # Update average entry
                    old_qty = self.state.position_qty - fill.quantity
                    total_value = self.state.position_price * old_qty + fill.price * fill.quantity
                    self.state.position_price = total_value / self.state.position_qty
                self.state.cash -= fill.price * fill.quantity + fill.fee
        else:  # sell/short
            if self.state.position_qty > 0:
                # Closing long
                pnl = (fill.price - self.state.position_price) * fill.quantity
                self.state.cash += fill.price * fill.quantity - fill.fee + pnl
                self.state.position_qty -= fill.quantity
            elif self.state.position_qty <= 0:
                # Adding to short or opening new short
                self.state.position_qty -= fill.quantity  # More negative
                self.state.cash += fill.price * fill.quantity - fill.fee  # Receive proceeds
                if self.state.position_qty < 0:
                    self.state.position_price = fill.price  # Update short entry

        # Log trade
        if self.config.log_trades:
            print(
                f"{fill.timestamp} | FILL: {fill.side.upper()} "
                f"{fill.quantity:.2f} @ {fill.price:.2f} | "
                f"Fee: ${fill.fee:.2f} Slippage: ${fill.slippage:.2f}"
            )

        # Record to trade list if it's an exit
        # (This is simplified; real implementation would track entry/exit pairs)

    def _update_equity(self, current_mid: float | None) -> None:
        """Update equity curve."""
        if current_mid is None:
            return

        unrealized_pnl = 0.0
        if self.state.position_qty > 0:
            unrealized_pnl = (current_mid - self.state.position_price) * self.state.position_qty
        elif self.state.position_qty < 0:
            unrealized_pnl = (self.state.position_price - current_mid) * abs(self.state.position_qty)

        self.state.equity = self.state.cash + unrealized_pnl

        self.state.equity_curve.append({
            "timestamp": self.state.current_time,
            "equity": self.state.equity,
        })

    def _compute_metrics(
        self, equity_df: pd.DataFrame, trades_df: pd.DataFrame
    ) -> dict:
        """Compute performance metrics."""
        if len(equity_df) < 2:
            return {}

        equity_df["returns"] = equity_df["equity"].pct_change()
        returns = equity_df["returns"].dropna()

        initial_equity = equity_df["equity"].iloc[0]
        final_equity = equity_df["equity"].iloc[-1]
        total_return = (final_equity / initial_equity) - 1

        # Annualized metrics (assuming data spans the period)
        n_periods = len(returns)
        if n_periods > 0:
            ann_factor = 365 * 24 * 3600 / (equity_df.index[-1] - equity_df.index[0]).total_seconds()
            ann_return = (1 + total_return) ** ann_factor - 1
            ann_vol = returns.std() * (ann_factor ** 0.5)
            sharpe = ann_return / ann_vol if ann_vol > 0 else 0
        else:
            ann_return = 0
            ann_vol = 0
            sharpe = 0

        # Drawdown
        rolling_max = equity_df["equity"].cummax()
        drawdown = (equity_df["equity"] - rolling_max) / rolling_max
        max_drawdown = drawdown.min()

        # Win rate
        winning = len(trades_df[trades_df["pnl"] > 0]) if len(trades_df) > 0 else 0
        total = len(trades_df)
        win_rate = winning / total if total > 0 else 0

        # Profit factor
        gross_profit = trades_df[trades_df["pnl"] > 0]["pnl"].sum() if len(trades_df) > 0 else 0
        gross_loss = abs(trades_df[trades_df["pnl"] < 0]["pnl"].sum()) if len(trades_df) > 0 else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        return {
            "total_return": total_return,
            "annual_return": ann_return,
            "annual_volatility": ann_vol,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "num_trades": total,
            "final_equity": final_equity,
        }
