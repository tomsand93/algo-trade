"""StateManager — atomic persistence for RiskManager state.

Provides two functions:
  save_state(risk_manager, state_file) -> None
    Atomically serializes all RiskManager state to disk using
    tempfile + os.replace() to prevent corruption on mid-write crashes.

  load_state(risk_manager, state_file) -> bool
    Deserializes state from disk into an existing RiskManager instance.
    Returns False (never raises) on missing or corrupt files.

IMPORTANT — Signal handler safety:
  save_state() must NEVER be called from a signal handler (SIGTERM/SIGINT).
  Call it only from the main thread after the event loop has exited cleanly.
  Signal handlers should set a flag; main thread checks flag and calls save_state().

Atomic write pattern (Windows-safe):
  os.replace() is atomic on Windows when src and dst are on the same filesystem.
  os.rename() fails on Windows if the destination file already exists — do not use it.
"""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger

from polymarket_bot.risk import RiskManager
from polymarket_bot.models import OpenPosition


def save_state(risk_manager: RiskManager, state_file: str) -> None:
    """Atomically write all RiskManager state to disk.

    Creates parent directories if they do not exist.
    Writes to a temp file first, then atomically replaces the target.
    On mid-write crash, the original file is left untouched.

    Args:
        risk_manager: The RiskManager instance whose state to persist.
        state_file:   Path to the JSON file (e.g. "data/state/positions.json").
    """
    path = Path(state_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "daily_pnl": risk_manager._daily_pnl,
        "portfolio_value": risk_manager._portfolio_value,
        "peak_value": risk_manager._peak_value,
        "halted": risk_manager._halted,
        "halt_reason": risk_manager._halt_reason,
        "positions": {
            mid: pos.model_dump(mode="json")
            for mid, pos in risk_manager._positions.items()
        },
        "last_trade_times": {
            mid: dt.isoformat()
            for mid, dt in risk_manager._last_trade_time.items()
        },
    }

    # Atomic write: write to temp file, then replace destination
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, str(path))
    except Exception:
        # Clean up temp file if replace failed
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    logger.info(
        "STATE SAVED | file={file} | positions={n_pos} | daily_pnl={pnl:.4f} | halted={halted}",
        file=state_file,
        n_pos=len(risk_manager._positions),
        pnl=risk_manager._daily_pnl,
        halted=risk_manager._halted,
    )


def load_state(risk_manager: RiskManager, state_file: str) -> bool:
    """Deserialize RiskManager state from disk into the given instance.

    Returns False immediately if the file does not exist.
    Returns False (and logs the error) if the JSON is corrupt or any
    field fails to deserialize — never raises.

    Args:
        risk_manager: The RiskManager instance to populate with saved state.
        state_file:   Path to the JSON file to read from.

    Returns:
        True on successful load, False on missing file or any error.
    """
    if not os.path.exists(state_file):
        logger.debug("STATE not found (fresh start) | file={file}", file=state_file)
        return False

    try:
        with open(state_file, "r") as f:
            data = json.load(f)

        # Restore scalar fields
        risk_manager._daily_pnl = float(data["daily_pnl"])
        risk_manager._portfolio_value = float(data["portfolio_value"])
        risk_manager._peak_value = float(data["peak_value"])
        risk_manager._halted = bool(data["halted"])
        risk_manager._halt_reason = str(data["halt_reason"])

        # Restore positions
        risk_manager._positions = {}
        for mid, pos_dict in data.get("positions", {}).items():
            risk_manager._positions[mid] = OpenPosition(**pos_dict)

        # Restore last trade times — parse ISO strings back to timezone-aware datetimes
        risk_manager._last_trade_time = {}
        for mid, iso_str in data.get("last_trade_times", {}).items():
            dt = datetime.fromisoformat(iso_str)
            # Ensure timezone-aware (fromisoformat preserves +00:00 offset)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            risk_manager._last_trade_time[mid] = dt

    except Exception as exc:
        logger.error(
            "STATE LOAD FAILED | file={file} | error={err}",
            file=state_file,
            err=str(exc),
        )
        return False

    logger.info(
        "STATE LOADED | file={file} | positions={n_pos} | daily_pnl={pnl:.4f} | halted={halted}",
        file=state_file,
        n_pos=len(risk_manager._positions),
        pnl=risk_manager._daily_pnl,
        halted=risk_manager._halted,
    )
    return True
