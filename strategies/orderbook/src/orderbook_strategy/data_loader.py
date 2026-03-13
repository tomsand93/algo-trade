"""Data loading and preprocessing for orderbook backtesting."""

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pandas as pd

from .events import BookLevel, BookSnapshot, Event, Trade, Side


def parse_timestamp(ts: str) -> datetime:
    """Parse timestamp from ISO8601 or unix ms."""
    ts = ts.strip()
    try:
        # Try unix ms first
        return datetime.fromtimestamp(float(ts) / 1000, tz=timezone.utc)
    except (ValueError, OSError):
        # Try ISO8601
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts).astimezone(timezone.utc)


def load_trades(path: Path) -> list[Trade]:
    """Load trades from CSV."""
    df = pd.read_csv(path)

    trades = []
    for _, row in df.iterrows():
        ts = parse_timestamp(str(row["timestamp"]))
        price = float(row["price"])
        size = float(row["size"])

        side = None
        if "side" in row and pd.notna(row["side"]):
            side_str = str(row["side"]).lower()
            side = Side.BUY if side_str == "buy" else Side.SELL

        trades.append(Trade(timestamp=ts, price=price, size=size, side=side))

    return trades


def load_orderbook(path: Path) -> list[BookSnapshot]:
    """Load orderbook snapshots from CSV.

    Expected columns: timestamp, side, level, price, size
    """
    df = pd.read_csv(path)
    df = df.sort_values("timestamp")

    # Group by timestamp
    snapshots_dict = defaultdict(lambda: {"bids": {}, "asks": {}})

    for _, row in df.iterrows():
        ts = parse_timestamp(str(row["timestamp"]))
        side_str = str(row["side"]).lower()
        level = int(row["level"])
        price = float(row["price"])
        size = float(row["size"])

        if side_str == "bid":
            snapshots_dict[ts]["bids"][level] = BookLevel(price=price, size=size)
        else:
            snapshots_dict[ts]["asks"][level] = BookLevel(price=price, size=size)

    # Convert to BookSnapshot objects
    snapshots = []
    for ts, data in sorted(snapshots_dict.items()):
        # Sort levels by price (bids descending, asks ascending)
        bids = sorted(data["bids"].values(), key=lambda x: x.price, reverse=True)
        asks = sorted(data["asks"].values(), key=lambda x: x.price)
        snapshots.append(BookSnapshot(timestamp=ts, bids=bids, asks=asks))

    return snapshots


def merge_events(trades: list[Trade], snapshots: list[BookSnapshot]) -> Iterator[Event]:
    """Merge trades and snapshots into a single monotonic event stream.

    Enforces strict timestamp ordering - yields events in timestamp order.
    BookSnapshots are processed BEFORE Trades at the same timestamp.
    """
    # Combine and sort
    all_events: list[Event] = list(trades) + list(snapshots)

    def get_sort_key(e: Event) -> tuple:
        """Return sort key (timestamp, type_priority).

        BookSnapshots (priority 0) come before Trades (priority 1).
        """
        if isinstance(e, Trade):
            return (e.timestamp, 1)
        elif isinstance(e, BookSnapshot):
            return (e.timestamp, 0)
        else:
            return (e.timestamp, 0)

    sorted_events = sorted(all_events, key=get_sort_key)

    # Assert monotonic
    prev_ts = None
    for event in sorted_events:
        curr_ts = event.timestamp if isinstance(event, (Trade, BookSnapshot)) else event.timestamp
        if prev_ts is not None and curr_ts < prev_ts:
            raise ValueError(f"Non-monotonic timestamp: {curr_ts} after {prev_ts}")
        prev_ts = curr_ts
        yield event


def infer_trade_side(trade: Trade, best_bid: float | None, best_ask: float | None) -> Side | None:
    """Infer trade side from price relative to best bid/ask."""
    if best_bid is None or best_ask is None:
        return None
    if trade.price >= best_ask:
        return Side.BUY
    elif trade.price <= best_bid:
        return Side.SELL
    return None
