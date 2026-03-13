"""Backtesting engine for Polymarket trading strategies.

Backtester: event-driven engine that replays list[MarketState] through the
existing strategy + risk stack, recording every fill and close into
TradeRecord list, then computes a BacktestReport with performance metrics.

Architecture mirrors run_loop() in run.py:
  Per tick: check_stops -> z_exit_check -> generate_signal -> should_trade
            -> risk.check -> fill (with slippage/fees) -> record_trade

Key differences from run_loop():
  - z_exit take-profit: exits if |z_score| <= z_exit_threshold (requires
    strategy to expose get_z_score())
  - Force-close at end of data (exit_reason="END_OF_DATA")
  - Records TradeRecord for every closed position
  - Does NOT log to console (logs are suppressed or minimal for batch runs)
  - Fresh RiskManager instantiated inside run() — no state bleed across calls

Slippage model:
  Buy entry:  fill_price = signal_price * (1 + slippage_pct), clamped to max 0.99
  Sell exit:  exit_price = current_price * (1 - slippage_pct), clamped to min 0.01

Fee model:
  fee = fill_price * quantity * fee_rate  (applied per trade on entry fill value)
  PnL = (exit_price - entry_price) * quantity - fee

Annualization note: Sharpe/Sortino use sqrt(252) convention (equity market convention
applied to prediction markets as approximation; documented in metrics.py).
"""
import dataclasses
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from loguru import logger

from polymarket_bot.metrics import max_drawdown, sharpe_ratio, sortino_ratio, win_rate
from polymarket_bot.models import MarketState, OpenPosition, SimulatedOrder
from polymarket_bot.risk import RiskManager

if TYPE_CHECKING:
    from polymarket_bot.strategy import BaseStrategy, MeanReversionStrategy


@dataclasses.dataclass
class TradeRecord:
    """Record of a single completed trade (entry + exit pair)."""
    market_id: str
    side: str           # "YES" or "NO"
    entry_price: float
    exit_price: float
    quantity: float
    entry_time: datetime
    exit_time: datetime
    pnl: float          # (exit_price - entry_price) * quantity - fees
    fees: float
    exit_reason: str    # "STOP_LOSS" | "SIGNAL_EXIT" | "END_OF_DATA"


@dataclasses.dataclass
class BacktestReport:
    """Full results of a completed backtest run."""
    strategy_name: str
    start_date: str         # ISO format string
    end_date: str           # ISO format string
    initial_capital: float
    final_capital: float
    total_return_pct: float
    sharpe_ratio: float | None
    sortino_ratio: float | None
    max_drawdown_pct: float
    win_rate_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_fees: float
    trades: list[dict]      # list of serialized TradeRecord dicts


def save_report(report: BacktestReport, output_path: str) -> None:
    """Serialize BacktestReport to JSON file with indent=2.

    Uses default=str for datetime objects embedded in trades list.
    Filename convention (caller's responsibility):
        backtest_{strategy}_{YYYYMMDD_HHMMSS}.json
    """
    report_dict = dataclasses.asdict(report)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2, default=str)
    logger.info("BACKTEST REPORT saved to {}", output_path)


class Backtester:
    """Event-driven backtester. Instantiate once; call run() for each dataset."""

    def __init__(
        self,
        strategy: "BaseStrategy",
        initial_capital: float,
        max_position_size: float,
        daily_loss_limit: float,
        stop_loss_pct: float,
        cooldown_seconds: int = 0,
        fee_rate: float = 0.0,
        slippage_pct: float = 0.005,
        z_exit_threshold: float | None = None,
    ) -> None:
        """
        Args:
            strategy: strategy instance (MeanReversionStrategy or MomentumStrategy)
            initial_capital: starting portfolio value in USD
            max_position_size: max USD per position (for capital-based qty sizing)
            daily_loss_limit: daily loss limit for RiskManager
            stop_loss_pct: per-position stop-loss fraction for RiskManager
            cooldown_seconds: cooldown period between trades per market (0 = no cooldown)
            fee_rate: fraction of fill value charged as fee (0.0 = fee-free)
            slippage_pct: fixed-pct slippage applied on entry and exit (0.005 = 0.5%)
            z_exit_threshold: if set and strategy has get_z_score(), exit when
                |z| <= z_exit_threshold. Defaults to strategy.z_exit if available.
        """
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.max_position_size = max_position_size
        self.daily_loss_limit = daily_loss_limit
        self.stop_loss_pct = stop_loss_pct
        self.cooldown_seconds = cooldown_seconds
        self.fee_rate = fee_rate
        self.slippage_pct = slippage_pct
        # Resolve z_exit_threshold: explicit param > strategy.z_exit attribute > None
        if z_exit_threshold is not None:
            self.z_exit_threshold = z_exit_threshold
        elif hasattr(strategy, "z_exit"):
            self.z_exit_threshold = strategy.z_exit
        else:
            self.z_exit_threshold = None

    def run(self, market_states: list[MarketState]) -> BacktestReport:
        """Run the backtest over a list of MarketState objects.

        A fresh RiskManager is instantiated for each call — no state bleed
        between runs. The strategy retains its own internal state across calls
        (rolling window history); callers should instantiate a fresh strategy
        per run if isolation is needed.

        Returns BacktestReport with all trades and computed metrics.
        """
        if not market_states:
            return self._empty_report()

        # Fresh RiskManager per run — prevents state bleed (Pitfall 2 from RESEARCH.md)
        risk_manager = RiskManager(
            initial_capital=self.initial_capital,
            max_position_size=self.max_position_size,
            daily_loss_limit=self.daily_loss_limit,
            stop_loss_pct=self.stop_loss_pct,
            cooldown_seconds=self.cooldown_seconds,
        )

        trades: list[TradeRecord] = []
        # Track last seen price per market for force-close at end of data
        last_prices: dict[str, tuple[float, float]] = {}  # market_id -> (yes_price, no_price)
        last_times: dict[str, datetime] = {}              # market_id -> last timestamp
        # Track entry info for trade recording (since RiskManager holds OpenPosition)
        # entry_fees per market: fee paid at entry (subtracted from pnl at close)
        entry_fees: dict[str, float] = {}
        entry_times: dict[str, datetime] = {}

        start_date = market_states[0].timestamp
        end_date = market_states[-1].timestamp

        for state in market_states:
            market_id = state.market_id
            last_prices[market_id] = (state.yes_price, state.no_price)
            last_times[market_id] = state.timestamp

            # Step 1: Check stop-loss for any open position in this market.
            # IMPORTANT: Capture pos BEFORE calling check_stops() because
            # check_stops() removes the position from _positions on fire.
            pos = risk_manager._positions.get(market_id)
            exit_signal = risk_manager.check_stops(state)
            if exit_signal is not None and pos is not None:
                # Stop-loss fired — exit at stop_loss_price with sell-side slippage
                exit_price_raw = pos.stop_loss_price
                exit_price = max(exit_price_raw * (1.0 - self.slippage_pct), 0.01)
                fee = entry_fees.pop(market_id, 0.0)
                pnl = round((exit_price - pos.entry_price) * pos.quantity - fee, 6)
                trades.append(TradeRecord(
                    market_id=market_id,
                    side=pos.side,
                    entry_price=pos.entry_price,
                    exit_price=exit_price,
                    quantity=pos.quantity,
                    entry_time=entry_times.pop(market_id, pos.opened_at),
                    exit_time=state.timestamp,
                    pnl=pnl,
                    fees=fee,
                    exit_reason="STOP_LOSS",
                ))
                continue  # position closed, move to next state

            # Step 2: Generate entry signal (also updates strategy's rolling window).
            # Must happen before z_exit check so get_z_score() reflects current price.
            signal = self.strategy.generate_signal(state)

            # Step 2b: z_exit take-profit check for open position.
            # Happens AFTER generate_signal() so the rolling window includes current price.
            pos = risk_manager._positions.get(market_id)
            if pos is not None and self.z_exit_threshold is not None:
                if hasattr(self.strategy, "get_z_score"):
                    z = self.strategy.get_z_score(market_id)
                    if z is not None and abs(z) <= self.z_exit_threshold:
                        # z returned to near mean — take profit
                        exit_price_raw = (
                            state.yes_price if pos.side == "YES" else state.no_price
                        )
                        exit_price = max(exit_price_raw * (1.0 - self.slippage_pct), 0.01)
                        fee = entry_fees.pop(market_id, 0.0)
                        pnl = round((exit_price - pos.entry_price) * pos.quantity - fee, 6)
                        trades.append(TradeRecord(
                            market_id=market_id,
                            side=pos.side,
                            entry_price=pos.entry_price,
                            exit_price=exit_price,
                            quantity=pos.quantity,
                            entry_time=entry_times.pop(market_id, pos.opened_at),
                            exit_time=state.timestamp,
                            pnl=pnl,
                            fees=fee,
                            exit_reason="SIGNAL_EXIT",
                        ))
                        risk_manager.record_close(market_id, exit_price)
                        continue

            # No open position — proceed with entry signal (if any)
            if signal is None:
                continue

            # Step 3: Confidence pre-filter
            if not self.strategy.should_trade(signal, state):
                continue

            # Step 4: Risk gate
            if not risk_manager.check(signal, state):
                continue

            # Step 5: Simulate fill with buy-side slippage
            fill_price = min(signal.price * (1.0 + self.slippage_pct), 0.99)
            quantity = round(self.max_position_size / fill_price, 4) if fill_price > 0 else 0.0
            if quantity <= 0:
                continue

            fee = round(fill_price * quantity * self.fee_rate, 6)
            entry_fees[market_id] = fee

            # Step 6: Record fill in RiskManager
            fill_time = state.timestamp
            stop_price = round(fill_price * (1.0 - self.stop_loss_pct), 4)
            # Clamp stop_price to valid range for OpenPosition validation
            stop_price = max(0.0, min(stop_price, 1.0))

            side = "YES" if "YES" in signal.direction else "NO"
            order = SimulatedOrder(
                market_id=market_id,
                side=side,
                direction="BUY",
                fill_price=fill_price,
                quantity=quantity,
                timestamp=fill_time,
            )
            risk_manager.record_fill(order, stop_price)
            entry_times[market_id] = fill_time

        # Force-close all remaining open positions at last seen price (END_OF_DATA)
        for market_id, pos in list(risk_manager._positions.items()):
            yes_p, no_p = last_prices.get(market_id, (pos.entry_price, 1.0 - pos.entry_price))
            exit_price_raw = yes_p if pos.side == "YES" else no_p
            exit_price = max(exit_price_raw * (1.0 - self.slippage_pct), 0.01)
            fee = entry_fees.pop(market_id, 0.0)
            pnl = round((exit_price - pos.entry_price) * pos.quantity - fee, 6)
            trades.append(TradeRecord(
                market_id=market_id,
                side=pos.side,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                quantity=pos.quantity,
                entry_time=entry_times.pop(market_id, pos.opened_at),
                exit_time=last_times.get(market_id, end_date),
                pnl=pnl,
                fees=fee,
                exit_reason="END_OF_DATA",
            ))

        return self._build_report(trades, start_date, end_date)

    def _build_report(
        self, trades: list[TradeRecord], start_date: datetime, end_date: datetime
    ) -> BacktestReport:
        """Compute metrics and build the BacktestReport from closed trade list."""
        pnls = [t.pnl for t in trades]
        total_pnl = sum(pnls)
        final_capital = round(self.initial_capital + total_pnl, 4)
        total_return_pct = (
            round((total_pnl / self.initial_capital) * 100.0, 4)
            if self.initial_capital > 0
            else 0.0
        )

        winners = [t for t in trades if t.pnl > 0]
        losers = [t for t in trades if t.pnl <= 0]

        # Build equity curve for max drawdown: cumulative capital after each trade
        equity_curve = [self.initial_capital]
        running = self.initial_capital
        for t in trades:
            running = round(running + t.pnl, 4)
            equity_curve.append(running)

        return BacktestReport(
            strategy_name=type(self.strategy).__name__,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            initial_capital=self.initial_capital,
            final_capital=final_capital,
            total_return_pct=total_return_pct,
            sharpe_ratio=sharpe_ratio(pnls),
            sortino_ratio=sortino_ratio(pnls),
            max_drawdown_pct=round(max_drawdown(equity_curve) * 100.0, 4),
            win_rate_pct=round(win_rate(pnls), 4),
            total_trades=len(trades),
            winning_trades=len(winners),
            losing_trades=len(losers),
            total_fees=round(sum(t.fees for t in trades), 6),
            trades=[dataclasses.asdict(t) for t in trades],
        )

    def _empty_report(self) -> BacktestReport:
        """Return a zero-trade report for empty input."""
        now = datetime.now(timezone.utc).isoformat()
        return BacktestReport(
            strategy_name=type(self.strategy).__name__,
            start_date=now,
            end_date=now,
            initial_capital=self.initial_capital,
            final_capital=self.initial_capital,
            total_return_pct=0.0,
            sharpe_ratio=None,
            sortino_ratio=None,
            max_drawdown_pct=0.0,
            win_rate_pct=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            total_fees=0.0,
            trades=[],
        )
