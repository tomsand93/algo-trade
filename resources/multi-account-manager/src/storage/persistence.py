"""
State persistence for crash recovery and restart safety.

Saves minimal state per account to JSON on disk. On restart, loads
the last known state so the manager can resume gracefully.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


class StatePersistence:
    """JSON-based state persistence for the manager."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.data_dir / "manager_state.json"
        self.events_file = self.data_dir / "events_today.json"

    def save_state(self, state: Dict[str, Any]):
        """Save the full manager state atomically."""
        state["saved_at"] = datetime.now().isoformat()

        # Write to temp file first, then rename (atomic on most OS)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, default=str))
        tmp.replace(self.state_file)
        log.debug("State saved to %s", self.state_file)

    def load_state(self) -> Optional[Dict[str, Any]]:
        """Load the last saved state, or None if no state file exists."""
        if not self.state_file.exists():
            return None
        try:
            return json.loads(self.state_file.read_text())
        except (json.JSONDecodeError, IOError) as e:
            log.warning("Failed to load state: %s", e)
            return None

    def save_events(self, events: List[Dict]):
        """Append events to today's event log."""
        existing = self.load_events()
        existing.extend(events)

        # Keep last 1000 events
        if len(existing) > 1000:
            existing = existing[-1000:]

        self.events_file.write_text(json.dumps(existing, indent=2, default=str))

    def load_events(self) -> List[Dict]:
        """Load today's events."""
        if not self.events_file.exists():
            return []
        try:
            return json.loads(self.events_file.read_text())
        except (json.JSONDecodeError, IOError):
            return []

    def clear_events(self):
        """Clear events file (call at start of new day)."""
        if self.events_file.exists():
            self.events_file.unlink()

    def save_account_state(self, account_name: str, account_state: Dict):
        """Save state for a single account."""
        path = self.data_dir / f"account_{account_name}_state.json"
        account_state["saved_at"] = datetime.now().isoformat()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(account_state, indent=2, default=str))
        tmp.replace(path)

    def load_account_state(self, account_name: str) -> Optional[Dict]:
        """Load state for a single account."""
        path = self.data_dir / f"account_{account_name}_state.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, IOError):
            return None
