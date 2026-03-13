"""Historical market data loader for backtesting.

load_csv(): loads from CSV file with columns:
    market_id, question, yes_price, no_price, volume_24h, timestamp (ISO 8601)
load_json(): loads from JSON array file with same fields.

Both functions:
- Return list[MarketState] sorted ascending by timestamp
- Skip malformed rows with a WARNING log (mirrors ReplayClient pattern)
- Normalize "Z" UTC suffix to "+00:00" for Python 3.10 fromisoformat compat
"""
import csv
import json
from datetime import datetime
from loguru import logger
from pydantic import ValidationError

from polymarket_bot.models import MarketState


def _parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO 8601 timestamp. Normalizes trailing Z for Python 3.10 compat."""
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))


def _row_to_market_state(row: dict, row_num: int, source: str) -> MarketState | None:
    """Convert a dict row to MarketState, returning None and logging on failure."""
    try:
        return MarketState(
            market_id=row["market_id"],
            question=row["question"],
            yes_price=float(row["yes_price"]),
            no_price=float(row["no_price"]),
            volume_24h=float(row["volume_24h"]),
            timestamp=_parse_timestamp(row["timestamp"]),
        )
    except (KeyError, ValueError, ValidationError) as exc:
        logger.warning("{}: skipping row {}: {}", source, row_num, exc)
        return None


def load_csv(path: str) -> list[MarketState]:
    """Load historical MarketState list from CSV file.

    Skips malformed rows with WARNING. Returns states sorted by timestamp ascending.
    Raises FileNotFoundError if path does not exist.
    """
    states = []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            state = _row_to_market_state(dict(row), i, f"CSV:{path}")
            if state is not None:
                states.append(state)
    states.sort(key=lambda s: s.timestamp)
    return states


def load_json(path: str) -> list[MarketState]:
    """Load historical MarketState list from JSON array file.

    Skips malformed rows with WARNING. Returns states sorted by timestamp ascending.
    Raises FileNotFoundError if path does not exist.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    states = []
    for i, row in enumerate(data, start=1):
        state = _row_to_market_state(row, i, f"JSON:{path}")
        if state is not None:
            states.append(state)
    states.sort(key=lambda s: s.timestamp)
    return states
