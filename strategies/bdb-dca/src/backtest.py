"""
Bar-by-bar backtest engine.
"""

from datetime import datetime, timezone
from typing import Optional

from .config import StrategyConfig
from .indicators import IndicatorState
from .models import Bar, BacktestResult
from .strategy import StrategyState
from .risk import RiskConfig, RiskEngine


def run_backtest(bars: list[Bar], config: StrategyConfig,
                 risk_config: Optional[RiskConfig] = None) -> BacktestResult:
    """
    Run the BDB DCA backtest over the given bars.

    Args:
        bars: Full bar list including warmup period
        config: Strategy configuration
        risk_config: Optional risk engine config (None = no risk management)

    Returns:
        BacktestResult with all metrics
    """
    # Parse trading window timestamps
    start_ms = _date_to_ms(config.start_date)
    stop_ms = _date_to_ms(config.stop_date)

    # Initialize indicator and strategy state
    indicators = IndicatorState(
        jaw_length=config.jaw_length,
        jaw_offset=config.jaw_offset,
        teeth_length=config.teeth_length,
        teeth_offset=config.teeth_offset,
        lips_length=config.lips_length,
        lips_offset=config.lips_offset,
        atr_length=config.atr_length,
        lowest_bars=config.lowest_bars,
    )
    strategy = StrategyState(config)

    # Initialize risk engine (optional)
    risk_engine = None
    if risk_config is not None:
        risk_engine = RiskEngine(risk_config)

    # Bar-by-bar loop
    for i, bar in enumerate(bars):
        # Update indicators first
        indicators.update(bar)

        # Determine if we're in the trading window
        in_window = start_ms <= bar.timestamp <= stop_ms

        # Risk engine: update state and check rules
        risk_can_enter = True
        if risk_engine is not None:
            # Track newly closed trades for risk reporting
            prev_closed_count = len(strategy.closed_trades)

            risk_engine.on_bar(
                bar.timestamp, strategy.equity,
                indicators.atr_value, bar.close
            )
            risk_can_enter = risk_engine.can_enter()

            # Cancel pending entries when risk engine first disables
            if risk_engine.just_disabled():
                strategy.pending_entries.clear()

        # Process strategy
        strategy.process_bar(i, bar, indicators, in_window, risk_can_enter)

        # Report newly closed trades to risk engine
        if risk_engine is not None:
            for trade in strategy.closed_trades[prev_closed_count:]:
                risk_engine.on_trade_closed(trade, bar.timestamp)

    # Force close any remaining positions at last bar's close
    if strategy.open_fills:
        last_bar = bars[-1]
        strategy.force_close_all(len(bars) - 1, last_bar.close)
        # Update final equity
        strategy.equity = strategy.cash

    result = BacktestResult(
        trades=strategy.closed_trades,
        final_equity=strategy.equity,
        initial_capital=config.initial_capital,
        peak_equity=strategy.peak_equity,
        max_drawdown=strategy.max_drawdown,
        equity_curve=strategy.equity_curve,
    )

    # Attach risk engine to result for inspection
    if risk_engine is not None:
        result.risk_engine = risk_engine

    return result


def _date_to_ms(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)
