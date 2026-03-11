"""
Tiered Exit System for Candlestick Pro

Implements progressive profit-taking through multiple exit levels:
- TP1: Close 40% at 1.5R (quick profit)
- TP2: Close 30% at 2.5R (solid gain)
- TP3: Close 30% at 3.5R or reversal (let winners run)

This allows locking in profits while maintaining upside potential.
"""
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from enum import Enum
import math

from src.models import Candle, Direction


class ExitReason(Enum):
    """Reason for position exit"""
    TIER_1 = "TP1 (1.5R)"
    TIER_2 = "TP2 (2.5R)"
    TIER_3 = "TP3 (3.5R)"
    STOP_LOSS = "Stop Loss"
    TRAILING_STOP = "Trailing Stop"
    REVERSAL = "Reversal Signal"
    END_OF_BACKTEST = "End of Backtest"


@dataclass
class TieredPosition:
    """
    Tracks a position with multiple exit tiers.

    Instead of closing the entire position at once, we track
    multiple "chunks" that can be exited independently at
    different price levels.
    """
    entry_price: float
    original_size: float  # Total original position size
    direction: Direction
    stop_loss: float
    original_stop: float
    entry_index: int
    entry_ts: str
    pattern: str
    original_risk: float  # Risk per unit in price terms

    # Position chunks - each chunk can be exited independently
    # List of (size, exit_level_rr, exit_price)
    chunks: List[Tuple[float, float, Optional[float]]] = None

    # Tracking for trailing stop
    highest_price: float = 0.0
    lowest_price: float = 0.0
    current_trail: float = 0.0

    # Track which tiers have been hit
    tiers_hit: List[int] = None

    def __post_init__(self):
        if self.chunks is None:
            self.chunks = []
        if self.tiers_hit is None:
            self.tiers_hit = []
        # Initialize tracking prices
        if self.highest_price == 0.0:
            self.highest_price = self.entry_price
            self.lowest_price = self.entry_price


def create_tiered_position(
    entry_price: float,
    size: float,
    direction: Direction,
    stop_loss: float,
    entry_index: int,
    entry_ts: str,
    pattern: str,
    tiered_exits: List[Tuple[float, float]]
) -> TieredPosition:
    """
    Create a tiered position from a standard entry.

    Args:
        entry_price: Entry price per unit
        size: Total position size
        direction: LONG or SHORT
        stop_loss: Stop loss price
        entry_index: Index of entry candle
        entry_ts: Entry timestamp
        pattern: Pattern type
        tiered_exits: List of (rr_level, percentage) tuples

    Returns:
        TieredPosition with chunks allocated to each tier
    """
    original_risk = abs(entry_price - stop_loss)

    # Create chunks for each tier
    chunks = []
    remaining_pct = 1.0

    for rr_level, pct in tiered_exits:
        chunk_size = size * pct
        # Calculate target price for this tier
        if direction == Direction.LONG:
            target_price = entry_price + (original_risk * rr_level)
        else:
            target_price = entry_price - (original_risk * rr_level)

        chunks.append((chunk_size, rr_level, target_price))
        remaining_pct -= pct

    # Handle any remaining position (rounding errors)
    if remaining_pct > 0.001:
        chunks.append((size * remaining_pct, tiered_exits[-1][0], chunks[-1][2]))

    return TieredPosition(
        entry_price=entry_price,
        original_size=size,
        direction=direction,
        stop_loss=stop_loss,
        original_stop=stop_loss,
        entry_index=entry_index,
        entry_ts=entry_ts,
        pattern=pattern,
        original_risk=original_risk,
        chunks=chunks,
        highest_price=entry_price,
        lowest_price=entry_price,
    )


def check_tiered_exit(
    position: TieredPosition,
    candle: Candle,
    atrs: List[float],
    index: int,
    config,
) -> Optional[Dict]:
    """
    Check if any position chunks should be exited.

    Handles:
    1. Tiered take profit levels
    2. Trailing stop (applies to all remaining chunks)
    3. Regular stop loss

    Returns dict with exit info if any chunk is exited, None otherwise.
    """
    direction = position.direction
    entry = position.entry_price
    original_risk = position.original_risk

    # Update price tracking
    if direction == Direction.LONG:
        position.highest_price = max(position.highest_price, candle.high)
    else:
        position.lowest_price = min(position.lowest_price, candle.low)

    # Trailing stop logic (same as original, applies to all chunks)
    if hasattr(config, 'use_trailing_stop') and config.use_trailing_stop and original_risk > 1e-10:
        current_atr = atrs[index] if index < len(atrs) and not math.isnan(atrs[index]) else original_risk

        if direction == Direction.LONG:
            unrealized_r = (position.highest_price - entry) / original_risk

            if unrealized_r >= 1.5:
                new_trail = position.highest_price - (current_atr * config.trailing_atr_distance)
                if new_trail > position.stop_loss:
                    position.stop_loss = new_trail
                    position.current_trail = new_trail
            elif unrealized_r >= config.breakeven_at_rr:
                if entry > position.stop_loss:
                    position.stop_loss = entry
        else:  # SHORT
            unrealized_r = (entry - position.lowest_price) / original_risk

            if unrealized_r >= 1.5:
                new_trail = position.lowest_price + (current_atr * config.trailing_atr_distance)
                if new_trail < position.stop_loss:
                    position.stop_loss = new_trail
                    position.current_trail = new_trail
            elif unrealized_r >= config.breakeven_at_rr:
                if entry < position.stop_loss:
                    position.stop_loss = entry

    # Check for exits
    exited_chunks = []
    remaining_chunks = []

    for chunk_size, rr_level, target_price in position.chunks:
        exit_price = None
        exit_reason = None

        if direction == Direction.LONG:
            # Check tiered TP
            if target_price and candle.high >= target_price:
                exit_price = max(target_price, candle.open)
                exit_reason = ExitReason.TIER_1 if rr_level == 1.5 else (
                    ExitReason.TIER_2 if rr_level == 2.5 else ExitReason.TIER_3
                )
            # Check stop loss
            elif candle.low <= position.stop_loss:
                exit_price = min(position.stop_loss, candle.open)
                exit_reason = ExitReason.TRAILING_STOP if position.stop_loss > position.original_stop else ExitReason.STOP_LOSS
        else:  # SHORT
            if target_price and candle.low <= target_price:
                exit_price = min(target_price, candle.open)
                exit_reason = ExitReason.TIER_1 if rr_level == 1.5 else (
                    ExitReason.TIER_2 if rr_level == 2.5 else ExitReason.TIER_3
                )
            elif candle.high >= position.stop_loss:
                exit_price = max(position.stop_loss, candle.open)
                exit_reason = ExitReason.TRAILING_STOP if position.stop_loss < position.original_stop else ExitReason.STOP_LOSS

        if exit_price:
            # Calculate PnL for this chunk
            if direction == Direction.LONG:
                pnl = chunk_size * (exit_price - entry)
            else:
                pnl = chunk_size * (entry - exit_price)

            exited_chunks.append({
                'size': chunk_size,
                'exit_price': exit_price,
                'pnl': pnl,
                'rr_level': rr_level,
                'reason': exit_reason,
            })
        else:
            remaining_chunks.append((chunk_size, rr_level, target_price))

    if exited_chunks:
        # Update position chunks
        position.chunks = remaining_chunks

        # Calculate totals for return
        total_exit_size = sum(c['size'] for c in exited_chunks)
        total_pnl = sum(c['pnl'] for c in exited_chunks)
        avg_exit_price = sum(c['exit_price'] * c['size'] for c in exited_chunks) / total_exit_size
        primary_reason = exited_chunks[0]['reason']

        return {
            'exited_chunks': exited_chunks,
            'total_size': total_exit_size,
            'total_pnl': total_pnl,
            'avg_exit_price': avg_exit_price,
            'reason': primary_reason,
            'is_partial': len(remaining_chunks) > 0,
        }

    return None


def close_remaining_position(
    position: TieredPosition,
    exit_price: float,
) -> Dict:
    """
    Close all remaining chunks of a position at a given price.

    Used for end-of-backtest closure or reversal signals.
    """
    total_pnl = 0
    total_size = 0
    chunk_details = []

    for chunk_size, rr_level, _ in position.chunks:
        if position.direction == Direction.LONG:
            pnl = chunk_size * (exit_price - position.entry_price)
        else:
            pnl = chunk_size * (position.entry_price - exit_price)

        total_pnl += pnl
        total_size += chunk_size
        chunk_details.append({
            'size': chunk_size,
            'exit_price': exit_price,
            'pnl': pnl,
            'rr_level': rr_level,
            'reason': ExitReason.END_OF_BACKTEST,
        })

    return {
        'exited_chunks': chunk_details,
        'total_size': total_size,
        'total_pnl': total_pnl,
        'avg_exit_price': exit_price,
        'reason': ExitReason.END_OF_BACKTEST,
        'is_partial': False,
    }
