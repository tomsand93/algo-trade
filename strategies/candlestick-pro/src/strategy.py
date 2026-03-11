"""
Candlestick Pro - Main Strategy Engine

Orchestrates timeframe selection, pattern detection, and trade management.
Includes confirmation candle logic, trailing stops, and multi-pattern scanning.
"""
from typing import Dict, List, Optional
import math
from src.models import (
    Candle, TradingIdea, PatternType, Direction, TimeFrameStyle,
    SupportResistanceLevel,
    BacktestConfig, BacktestResult
)
from src.indicators import (
    compute_atr, detect_support_resistance,
    compute_rsi, compute_ema, compute_volume_ratio,
)
from src.timeframe_selector import TimeframeSelector
from src.patterns import PatternDetector
from src.trade_manager import TradeManager
from src.tiered_exit import (
    create_tiered_position,
    check_tiered_exit,
    close_remaining_position,
)

EPSILON = 1e-10


class CandlestickStrategy:
    """
    Main strategy implementing the candlestick pattern trading system.

    Process:
    1. Load/analyze multiple timeframes
    2. Dynamically select best timeframe
    3. Detect high-quality pattern (multi-pattern or single)
    4. Wait for confirmation candle
    5. Generate trading idea with dynamic SL/TP + trailing stop
    6. Validate against trade filters
    """

    def __init__(
        self,
        pattern_type: PatternType = PatternType.ENGULFING,
        style: TimeFrameStyle = TimeFrameStyle.INTRADAY,
        min_rr_ratio: float = 2.0,
        min_confidence: float = 0.60
    ):
        self.pattern_type = pattern_type
        self.style = style
        self.min_rr_ratio = min_rr_ratio
        self.min_confidence = min_confidence

        # Initialize components
        self.tf_selector = TimeframeSelector(preferred_style=style)
        self.pattern_detector = PatternDetector()
        self.trade_manager = TradeManager(min_rr_ratio=min_rr_ratio)

    def analyze(
        self,
        timeframe_data: Dict[str, List[Candle]],
        symbol: str
    ) -> Optional[TradingIdea]:
        """
        Analyze market data and generate a trading idea.

        Args:
            timeframe_data: Dict of timeframe -> candle list
            symbol: Trading symbol

        Returns:
            TradingIdea if valid setup found, None otherwise
        """
        if not timeframe_data:
            return None

        # Step 1: Select best timeframe
        selected_tf, tf_analysis = self.tf_selector.select_best_timeframe(timeframe_data)
        candles = timeframe_data[selected_tf]

        if len(candles) < 50:
            return None

        # Step 2: Detect support/resistance levels
        sr_levels = detect_support_resistance(candles)

        # Step 3: Detect pattern (multi-pattern: scan all, pick best)
        pattern_result = self._find_best_pattern(candles, sr_levels)

        if not pattern_result:
            return None

        # Step 4: Create trading idea
        idea = self.trade_manager.create_trading_idea(
            pattern_result=pattern_result,
            candles=candles,
            sr_levels=sr_levels,
            symbol=symbol,
            timeframe=selected_tf,
            timeframe_justification=tf_analysis.reason
        )

        if not idea:
            return None

        # Step 5: Validate filters
        passed, passed_filters, failed_filters = self.trade_manager.validate_filters(idea, candles)

        idea.filters_passed = passed_filters
        idea.filters_failed = failed_filters

        if not passed:
            return None

        return idea

    def _find_best_pattern(
        self,
        candles: List[Candle],
        sr_levels: List[SupportResistanceLevel],
        rsi_values: Optional[List[float]] = None,
        ema9: Optional[List[float]] = None,
        ema21: Optional[List[float]] = None,
        volume_ratios: Optional[List[float]] = None,
    ) -> Optional[Dict]:
        """
        Scan all 5 pattern types, return the highest-confidence one.

        Precomputed indicators can be passed to avoid recomputation.
        """
        # Precompute indicators once for all patterns
        if rsi_values is None:
            rsi_values = compute_rsi(candles, 14)
        if ema9 is None:
            ema9 = compute_ema(candles, 9)
        if ema21 is None:
            ema21 = compute_ema(candles, 21)
        if volume_ratios is None:
            volume_ratios = compute_volume_ratio(candles, 20)

        best_result = None
        best_confidence = 0.0

        for pt in PatternType:
            result = self.pattern_detector.detect(
                candles, pt, sr_levels, self.min_confidence,
                rsi_values=rsi_values,
                ema9=ema9,
                ema21=ema21,
                volume_ratios=volume_ratios,
            )
            if result and result.get("confidence", 0) > best_confidence:
                best_confidence = result["confidence"]
                best_result = result

        return best_result

    def backtest(
        self,
        candles: List[Candle],
        config: BacktestConfig
    ) -> BacktestResult:
        """
        Run backtest on single timeframe data.

        Simulates trades walking through historical data with:
        - No lookahead bias (S/R computed per-step)
        - Confirmation candle requirement
        - Trailing stop management
        - Multi-pattern scanning
        """
        if len(candles) < 100:
            return BacktestResult(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                total_return=0.0,
                max_drawdown=0.0,
                max_drawdown_pct=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                expectancy=0.0,
                profit_factor=0.0,
                total_fees=0.0,
                equity_curve=[config.initial_capital],
                trades=[]
            )

        # Apply strict_trend setting from config
        if hasattr(config, 'strict_trend'):
            self.pattern_detector.config["confluence"]["strict_trend"] = config.strict_trend

        # Precompute ATR for trailing stop use
        full_atrs = compute_atr(candles, 14)

        cash = config.initial_capital
        position = None
        trades = []
        equity_curve = [cash]

        # Pending signal awaiting confirmation
        pending_signal = None  # {idea, signal_index, direction, pattern_high, pattern_low}

        # Walk through candles
        for i in range(50, len(candles)):
            # Update equity if in position
            if position:
                if position['direction'] == Direction.LONG:
                    unrealized = position['size'] * (candles[i].close - position['entry_price'])
                else:
                    unrealized = position['size'] * (position['entry_price'] - candles[i].close)
                # Cash already reduced by entry cost; add back position value
                current_value = cash + position['size'] * position['entry_price'] + unrealized
                equity_curve.append(current_value)
            else:
                equity_curve.append(cash)

            # Check exit for existing position (with trailing stop)
            if position:
                exit_result = self._check_exit(position, candles[i], i, config, full_atrs)
                if exit_result:
                    # Return original investment + profit/loss
                    cash += position['size'] * position['entry_price'] + exit_result['pnl']
                    trades.append(exit_result['trade'])
                    position = None
                    continue

            # Check pending confirmation
            if pending_signal and position is None:
                conf = pending_signal
                candles_waited = i - conf['signal_index']

                if candles_waited > config.confirmation_window:
                    # Confirmation window expired — skip
                    pending_signal = None
                else:
                    # Check if this candle confirms the pattern
                    confirmed = self._check_confirmation(
                        candles[i], conf['direction'],
                        conf['pattern_high'], conf['pattern_low']
                    )
                    if confirmed:
                        idea = conf['idea']
                        entry_price = candles[i].close  # Enter at confirmation close
                        risk = abs(entry_price - idea.stop_loss_price)
                        size = self._calculate_position_size(cash, entry_price, risk, config.fee_pct)

                        if size > 0:
                            fee = size * entry_price * config.fee_pct
                            position = {
                                'entry_price': entry_price,
                                'size': size,
                                'direction': idea.direction,
                                'stop_loss': idea.stop_loss_price,
                                'original_stop': idea.stop_loss_price,
                                'take_profit': idea.take_profit_prices[0],
                                'entry_index': i,
                                'pattern': idea.pattern.value,
                                'entry_ts': candles[i].timestamp,
                                'highest_price': entry_price,
                                'lowest_price': entry_price,
                            }
                            cash -= (size * entry_price + fee)
                        pending_signal = None
                        continue

            # Look for new entry (if no position and no pending)
            if position is None and pending_signal is None:
                # Compute S/R on historical data only (no lookahead)
                sr_levels = detect_support_resistance(candles[:i+1])

                # Precompute indicators on the historical slice
                hist = candles[:i+1]
                rsi_vals = compute_rsi(hist, 14)
                e9 = compute_ema(hist, 9)
                e21 = compute_ema(hist, 21)
                vol_ratios = compute_volume_ratio(hist, 20)

                # Multi-pattern or single pattern detection
                if config.use_multi_pattern:
                    pattern_result = self._find_best_pattern(
                        hist, sr_levels,
                        rsi_values=rsi_vals, ema9=e9,
                        ema21=e21, volume_ratios=vol_ratios,
                    )
                else:
                    pattern_result = self.pattern_detector.detect(
                        hist, self.pattern_type, sr_levels,
                        self.min_confidence,
                        rsi_values=rsi_vals, ema9=e9,
                        ema21=e21, volume_ratios=vol_ratios,
                    )

                if pattern_result:
                    idea = self.trade_manager.create_trading_idea(
                        pattern_result=pattern_result,
                        candles=hist,
                        sr_levels=sr_levels,
                        symbol=config.symbol,
                        timeframe="backtest",
                        timeframe_justification="Backtest mode"
                    )

                    if idea and idea.rr_ratio >= config.min_rr_ratio:
                        if config.use_confirmation:
                            # Store as pending — wait for confirmation candle
                            pattern_candles = pattern_result['candles']
                            pattern_high = max(c.high for c in pattern_candles)
                            pattern_low = min(c.low for c in pattern_candles)

                            pending_signal = {
                                'idea': idea,
                                'signal_index': i,
                                'direction': idea.direction,
                                'pattern_high': pattern_high,
                                'pattern_low': pattern_low,
                            }
                        else:
                            # No confirmation — enter at next open (old behavior)
                            if i + 1 < len(candles):
                                entry_price = candles[i + 1].open
                                risk = abs(idea.entry_price - idea.stop_loss_price)
                                size = self._calculate_position_size(cash, entry_price, risk, config.fee_pct)

                                if size > 0:
                                    fee = size * entry_price * config.fee_pct
                                    position = {
                                        'entry_price': entry_price,
                                        'size': size,
                                        'direction': idea.direction,
                                        'stop_loss': idea.stop_loss_price,
                                        'original_stop': idea.stop_loss_price,
                                        'take_profit': idea.take_profit_prices[0],
                                        'entry_index': i + 1,
                                        'pattern': idea.pattern.value,
                                        'entry_ts': candles[i + 1].timestamp,
                                        'highest_price': entry_price,
                                        'lowest_price': entry_price,
                                    }
                                    cash -= (size * entry_price + fee)

        # Close remaining position
        if position:
            last_candle = candles[-1]
            exit_price = last_candle.close
            pnl = self._calculate_pnl(position, exit_price, config)
            cash += position['size'] * position['entry_price'] + pnl
            trades.append({
                'entry_ts': position['entry_ts'],
                'exit_ts': last_candle.timestamp,
                'pattern': position['pattern'],
                'direction': position['direction'].value,
                'entry': position['entry_price'],
                'exit': exit_price,
                'pnl': pnl,
                'bars': len(candles) - position['entry_index'],
                'reason': 'End of data'
            })
            equity_curve.append(cash)

        return self._compute_backtest_metrics(trades, equity_curve, config)

    def backtest_tiered(
        self,
        candles: List[Candle],
        config: BacktestConfig,
    ) -> BacktestResult:
        """
        Run backtest with tiered exit system.

        Progressive profit-taking:
        - TP1: Close 40% at 1.5R (quick profit)
        - TP2: Close 30% at 2.5R (solid gain)
        - TP3: Close 30% at 3.5R or reversal (let winners run)

        This allows locking in profits while maintaining upside potential.
        """
        if len(candles) < 100:
            return BacktestResult(
                total_trades=0, winning_trades=0, losing_trades=0,
                win_rate=0.0, total_return=0.0, max_drawdown=0.0,
                max_drawdown_pct=0.0, avg_win=0.0, avg_loss=0.0,
                expectancy=0.0, profit_factor=0.0, total_fees=0.0,
                equity_curve=[config.initial_capital], trades=[]
            )

        # Apply strict_trend setting
        if hasattr(config, 'strict_trend'):
            self.pattern_detector.config["confluence"]["strict_trend"] = config.strict_trend

        # Precompute ATR
        full_atrs = compute_atr(candles, 14)

        cash = config.initial_capital
        position = None  # Will be TieredPosition if tiered exits enabled
        trades = []
        equity_curve = [cash]
        pending_signal = None

        # Track partial exits separately (each exit is a separate trade record)
        partial_exits = []  # List of exit dicts for current position

        for i in range(50, len(candles)):
            # Update equity
            if position:
                # Calculate remaining position size from chunks
                remaining_size = sum(chunk[0] for chunk in position.chunks)

                if position.direction == Direction.LONG:
                    unrealized = 0
                    for chunk_size, _, _ in position.chunks:
                        unrealized += chunk_size * (candles[i].close - position.entry_price)
                else:
                    unrealized = 0
                    for chunk_size, _, _ in position.chunks:
                        unrealized += chunk_size * (position.entry_price - candles[i].close)
                current_value = cash + remaining_size * position.entry_price + unrealized
                equity_curve.append(current_value)
            else:
                equity_curve.append(cash)

            # Check exit for existing position
            if position:
                exit_result = check_tiered_exit(position, candles[i], full_atrs, i, config)
                if exit_result:
                    # Add to partial exits list
                    partial_exits.append(exit_result)

                    # Update cash: return original capital for exited chunk + PnL
                    chunk_capital = exit_result['total_size'] * position.entry_price
                    cash += chunk_capital + exit_result['total_pnl']

                    # If this was the final exit (no chunks remaining), record the complete trade
                    if not exit_result['is_partial']:
                        # Combine all partial exits into a single trade record
                        total_pnl = sum(e['total_pnl'] for e in partial_exits)
                        avg_entry = position.entry_price

                        # Calculate weighted average exit
                        total_exit_size = sum(e['total_size'] for e in partial_exits)
                        avg_exit = sum(e['avg_exit_price'] * e['total_size'] for e in partial_exits) / total_exit_size

                        # Determine primary reason (first TP or stop loss)
                        primary_reason = partial_exits[0]['reason'].value

                        trades.append({
                            'entry_ts': position.entry_ts,
                            'exit_ts': candles[i].timestamp,
                            'pattern': position.pattern,
                            'direction': position.direction.value,
                            'entry': avg_entry,
                            'exit': avg_exit,
                            'pnl': total_pnl,
                            'bars': i - position.entry_index,
                            'reason': primary_reason,
                            'partial_exits': len(partial_exits),
                        })

                        position = None
                        partial_exits = []
                    continue

            # Check pending confirmation (same as original backtest)
            if pending_signal and position is None:
                conf = pending_signal
                candles_waited = i - conf['signal_index']

                if candles_waited > config.confirmation_window:
                    pending_signal = None
                else:
                    confirmed = self._check_confirmation(
                        candles[i], conf['direction'],
                        conf['pattern_high'], conf['pattern_low']
                    )
                    if confirmed:
                        idea = conf['idea']
                        entry_price = candles[i].close
                        risk = abs(entry_price - idea.stop_loss_price)
                        size = self._calculate_position_size(cash, entry_price, risk, config.fee_pct)

                        if size > 0:
                            fee = size * entry_price * config.fee_pct

                            # Create tiered position
                            tiered_exits = config.tiered_exits if hasattr(config, 'tiered_exits') else [
                                (1.5, 0.40), (2.5, 0.30), (3.5, 0.30)
                            ]
                            position = create_tiered_position(
                                entry_price=entry_price,
                                size=size,
                                direction=idea.direction,
                                stop_loss=idea.stop_loss_price,
                                entry_index=i,
                                entry_ts=candles[i].timestamp,
                                pattern=idea.pattern.value,
                                tiered_exits=tiered_exits,
                            )
                            cash -= (size * entry_price + fee)
                        pending_signal = None
                        continue

            # Look for new entry (if no position and no pending)
            if position is None and pending_signal is None:
                sr_levels = detect_support_resistance(candles[:i+1])
                hist = candles[:i+1]
                rsi_vals = compute_rsi(hist, 14)
                e9 = compute_ema(hist, 9)
                e21 = compute_ema(hist, 21)
                vol_ratios = compute_volume_ratio(hist, 20)

                if config.use_multi_pattern:
                    pattern_result = self._find_best_pattern(
                        hist, sr_levels,
                        rsi_values=rsi_vals, ema9=e9,
                        ema21=e21, volume_ratios=vol_ratios,
                    )
                else:
                    pattern_result = self.pattern_detector.detect(
                        hist, self.pattern_type, sr_levels,
                        self.min_confidence,
                        rsi_values=rsi_vals, ema9=e9,
                        ema21=e21, volume_ratios=vol_ratios,
                    )

                if pattern_result:
                    idea = self.trade_manager.create_trading_idea(
                        pattern_result=pattern_result,
                        candles=hist,
                        sr_levels=sr_levels,
                        symbol=config.symbol,
                        timeframe="backtest",
                        timeframe_justification="Backtest mode"
                    )

                    if idea and idea.rr_ratio >= config.min_rr_ratio:
                        if config.use_confirmation:
                            pattern_candles = pattern_result['candles']
                            pattern_high = max(c.high for c in pattern_candles)
                            pattern_low = min(c.low for c in pattern_candles)

                            pending_signal = {
                                'idea': idea,
                                'signal_index': i,
                                'direction': idea.direction,
                                'pattern_high': pattern_high,
                                'pattern_low': pattern_low,
                            }
                        else:
                            if i + 1 < len(candles):
                                entry_price = candles[i + 1].open
                                risk = abs(idea.entry_price - idea.stop_loss_price)
                                size = self._calculate_position_size(cash, entry_price, risk, config.fee_pct)

                                if size > 0:
                                    fee = size * entry_price * config.fee_pct
                                    tiered_exits = config.tiered_exits if hasattr(config, 'tiered_exits') else [
                                        (1.5, 0.40), (2.5, 0.30), (3.5, 0.30)
                                    ]
                                    position = create_tiered_position(
                                        entry_price=entry_price,
                                        size=size,
                                        direction=idea.direction,
                                        stop_loss=idea.stop_loss_price,
                                        entry_index=i + 1,
                                        entry_ts=candles[i + 1].timestamp,
                                        pattern=idea.pattern.value,
                                        tiered_exits=tiered_exits,
                                    )
                                    cash -= (size * entry_price + fee)

        # Close remaining position at end of backtest
        if position:
            last_candle = candles[-1]
            exit_result = close_remaining_position(position, last_candle.close)
            # Add back original capital + PnL
            remaining_capital = exit_result['total_size'] * position.entry_price
            cash += remaining_capital + exit_result['total_pnl']

            # Record final trade
            if partial_exits:
                # Combine partial exits with final close
                total_pnl = sum(e['total_pnl'] for e in partial_exits) + exit_result['total_pnl']
                partial_exits.append(exit_result)

                avg_exit = sum(e['avg_exit_price'] * e['total_size'] for e in partial_exits) / position.original_size
            else:
                total_pnl = exit_result['total_pnl']
                avg_exit = exit_result['avg_exit_price']

            trades.append({
                'entry_ts': position.entry_ts,
                'exit_ts': last_candle.timestamp,
                'pattern': position.pattern,
                'direction': position.direction.value,
                'entry': position.entry_price,
                'exit': avg_exit,
                'pnl': total_pnl,
                'bars': len(candles) - position.entry_index,
                'reason': exit_result['reason'].value,
                'partial_exits': len(partial_exits) + 1,
            })
            equity_curve.append(cash)

        return self._compute_backtest_metrics(trades, equity_curve, config)

    def _calculate_position_size(
        self, cash: float, entry_price: float, risk: float,
        fee_pct: float, max_capital_pct: float = 0.20
    ) -> float:
        """
        Calculate position size with proper capital constraints.

        Risk-based sizing: risk 1% of cash per trade.
        Cap: notional value never exceeds max_capital_pct of cash.
        """
        if risk <= EPSILON or entry_price <= EPSILON:
            return 0.0

        risk_amount = cash * 0.01
        size_from_risk = risk_amount / risk

        # Cap so notional value doesn't exceed max_capital_pct of cash
        max_notional = cash * max_capital_pct
        max_size = max_notional / entry_price
        size = min(size_from_risk, max_size)

        # Verify we can afford entry + fee
        fee = size * entry_price * fee_pct
        if cash < fee + size * entry_price:
            size = (cash * 0.95) / (entry_price * (1 + fee_pct))

        return max(0.0, size)

    def _check_confirmation(
        self,
        candle: Candle,
        direction: Direction,
        pattern_high: float,
        pattern_low: float,
    ) -> bool:
        """
        Check if a candle confirms the pattern direction.

        Uses midpoint of pattern range — a softer check than requiring
        close above the full pattern high, which rejects ~75% of valid setups.

        LONG: candle must close above the pattern midpoint AND be bullish.
        SHORT: candle must close below the pattern midpoint AND be bearish.
        """
        midpoint = (pattern_high + pattern_low) / 2

        if direction == Direction.LONG:
            return candle.close > midpoint and candle.is_bullish
        else:
            return candle.close < midpoint and not candle.is_bullish

    def _check_exit(
        self,
        position: dict,
        candle: Candle,
        index: int,
        config: BacktestConfig,
        atrs: List[float],
    ) -> Optional[dict]:
        """
        Check if position should be exited.

        Includes trailing stop logic:
        - After 1R profit: move stop to breakeven
        - After 1.5R profit: trail at trailing_atr_distance * ATR
        """
        direction = position['direction']
        sl = position['stop_loss']
        tp = position['take_profit']
        entry = position['entry_price']
        original_risk = abs(entry - position['original_stop'])

        # Update price tracking
        if direction == Direction.LONG:
            position['highest_price'] = max(position['highest_price'], candle.high)
        else:
            position['lowest_price'] = min(position['lowest_price'], candle.low)

        # Trailing stop logic
        if config.use_trailing_stop and original_risk > EPSILON:
            current_atr = atrs[index] if index < len(atrs) and not math.isnan(atrs[index]) else original_risk

            if direction == Direction.LONG:
                unrealized_r = (position['highest_price'] - entry) / original_risk

                if unrealized_r >= 1.5:
                    # Trail at ATR distance below highest price
                    new_trail = position['highest_price'] - (current_atr * config.trailing_atr_distance)
                    if new_trail > sl:
                        position['stop_loss'] = new_trail
                        sl = new_trail
                elif unrealized_r >= config.breakeven_at_rr:
                    # Move to breakeven
                    if entry > sl:
                        position['stop_loss'] = entry
                        sl = entry
            else:  # SHORT
                unrealized_r = (entry - position['lowest_price']) / original_risk

                if unrealized_r >= 1.5:
                    new_trail = position['lowest_price'] + (current_atr * config.trailing_atr_distance)
                    if new_trail < sl:
                        position['stop_loss'] = new_trail
                        sl = new_trail
                elif unrealized_r >= config.breakeven_at_rr:
                    if entry < sl:
                        position['stop_loss'] = entry
                        sl = entry

        # Check SL/TP hits with realistic gap handling
        # If candle gaps through a level, use the open (gap price), not the level
        exit_price = None
        reason = None

        if direction == Direction.LONG:
            sl_hit = candle.low <= sl
            tp_hit = candle.high >= tp

            if sl_hit and tp_hit:
                # Both hit — assume SL hit first (conservative)
                exit_price = min(sl, candle.open)  # Gap down = exit at open
                reason = 'Stop Loss' if sl <= position['original_stop'] else 'Trailing Stop'
            elif sl_hit:
                exit_price = min(sl, candle.open)  # Gap protection
                reason = 'Stop Loss' if sl <= position['original_stop'] else 'Trailing Stop'
            elif tp_hit:
                exit_price = max(tp, candle.open)  # Gap up = exit at open (better than TP)
                reason = 'Take Profit'
        else:  # SHORT
            sl_hit = candle.high >= sl
            tp_hit = candle.low <= tp

            if sl_hit and tp_hit:
                # Both hit — assume SL hit first (conservative)
                exit_price = max(sl, candle.open)  # Gap up = exit at open
                reason = 'Stop Loss' if sl >= position['original_stop'] else 'Trailing Stop'
            elif sl_hit:
                exit_price = max(sl, candle.open)  # Gap protection
                reason = 'Stop Loss' if sl >= position['original_stop'] else 'Trailing Stop'
            elif tp_hit:
                exit_price = min(tp, candle.open)  # Gap down = exit at open (better than TP)
                reason = 'Take Profit'

        if exit_price:
            pnl = self._calculate_pnl(position, exit_price, config)
            return {
                'pnl': pnl,
                'trade': {
                    'entry_ts': position['entry_ts'],
                    'exit_ts': candle.timestamp,
                    'pattern': position['pattern'],
                    'direction': position['direction'].value,
                    'entry': position['entry_price'],
                    'exit': exit_price,
                    'pnl': pnl,
                    'bars': index - position['entry_index'],
                    'reason': reason
                }
            }

        return None

    def _calculate_pnl(self, position: dict, exit_price: float, config: BacktestConfig) -> float:
        """Calculate PnL including fees and slippage."""
        direction = position['direction']
        size = position['size']
        entry = position['entry_price']

        # Apply slippage
        if direction == Direction.LONG:
            actual_exit = exit_price * (1 - config.slippage_pct)
            gross_pnl = size * (actual_exit - entry)
        else:
            actual_exit = exit_price * (1 + config.slippage_pct)
            gross_pnl = size * (entry - actual_exit)

        # Exit fee
        exit_fee = size * actual_exit * config.fee_pct

        return gross_pnl - exit_fee

    def _compute_backtest_metrics(
        self,
        trades: List[dict],
        equity_curve: List[float],
        config: BacktestConfig
    ) -> BacktestResult:
        """Compute backtest performance metrics."""
        if not trades:
            return BacktestResult(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                total_return=0.0,
                max_drawdown=0.0,
                max_drawdown_pct=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                expectancy=0.0,
                profit_factor=0.0,
                total_fees=0.0,
                equity_curve=equity_curve,
                trades=[]
            )

        total_trades = len(trades)
        wins = [t for t in trades if t['pnl'] > 0]
        losses = [t for t in trades if t['pnl'] <= 0]

        winning_trades = len(wins)
        losing_trades = len(losses)
        win_rate = winning_trades / total_trades

        avg_win = sum(t['pnl'] for t in wins) / winning_trades if wins else 0
        avg_loss = sum(t['pnl'] for t in losses) / losing_trades if losses else 0

        total_return = (equity_curve[-1] - config.initial_capital) / config.initial_capital
        expectancy = sum(t['pnl'] for t in trades) / total_trades

        gross_profit = sum(t['pnl'] for t in wins)
        gross_loss = abs(sum(t['pnl'] for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > EPSILON else float('inf')

        # Max drawdown
        peak = equity_curve[0]
        max_dd = 0.0
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        return BacktestResult(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_return=total_return,
            max_drawdown=max_dd * config.initial_capital,
            max_drawdown_pct=max_dd,
            avg_win=avg_win,
            avg_loss=avg_loss,
            expectancy=expectancy,
            profit_factor=profit_factor,
            total_fees=0.0,  # Already included in PnL
            equity_curve=equity_curve,
            trades=trades
        )
