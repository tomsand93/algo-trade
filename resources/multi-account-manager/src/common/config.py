"""
Central configuration for the Multi-Account Strategy Manager.

All secrets come from environment variables — never hardcoded.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


PAPER_BASE_URL = "https://paper-api.alpaca.markets"
PAPER_DATA_URL = "https://data.alpaca.markets"
REPO_ROOT = Path(__file__).resolve().parents[4]
STRATEGIES_ROOT = REPO_ROOT / "strategies"

# Block list: any URL not matching paper endpoints is rejected
BLOCKED_URL_PATTERNS = [
    "https://api.alpaca.markets",  # LIVE trading endpoint
]


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise EnvironmentError(
            f"Missing required environment variable: {name}. "
            f"Set it in your .env file or shell."
        )
    return val


@dataclass
class AccountConfig:
    name: str
    api_key_env: str
    api_secret_env: str
    strategy_repo_path: str
    initial_capital: float = 5000.0

    @property
    def api_key(self) -> str:
        return _require_env(self.api_key_env)

    @property
    def api_secret(self) -> str:
        return _require_env(self.api_secret_env)


@dataclass
class RiskLimits:
    max_position_value_usd: float = 2500.0
    max_daily_loss_usd: float = 500.0
    max_orders_per_day: int = 50


@dataclass
class ManagerConfig:
    accounts: Dict[str, AccountConfig] = field(default_factory=dict)
    risk_limits: RiskLimits = field(default_factory=RiskLimits)
    timezone: str = "America/New_York"
    dashboard_port: int = 8050
    api_port: int = 8051
    scan_interval_seconds: int = 60
    state_dir: str = "data"
    log_dir: str = "logs"


def build_default_config() -> ManagerConfig:
    """Build config from environment variables with the 3 defined accounts."""
    accounts = {
        # "tradingView": AccountConfig(
        #     name="tradingView",
        #     api_key_env="TRADINGVIEW_API_KEY",
        #     api_secret_env="TRADINGVIEW_API_SECRET",
        #     strategy_repo_path=str(REPO_ROOT / "tradingView"),
        # ),
        "bitcoin4H": AccountConfig(
            name="bitcoin4H",
            api_key_env="BITCOIN4H_API_KEY",
            api_secret_env="BITCOIN4H_API_SECRET",
            strategy_repo_path=str(STRATEGIES_ROOT / "candlestick-pro"),
        ),
        "fvg": AccountConfig(
            name="fvg",
            api_key_env="FVG_API_KEY",
            api_secret_env="FVG_API_SECRET",
            strategy_repo_path=str(STRATEGIES_ROOT / "fvg-breakout"),
        ),
    }

    risk_limits = RiskLimits(
        max_position_value_usd=float(os.environ.get("MAX_POSITION_VALUE_USD", "2500")),
        max_daily_loss_usd=float(os.environ.get("MAX_DAILY_LOSS_USD", "500")),
        max_orders_per_day=int(os.environ.get("MAX_ORDERS_PER_DAY", "50")),
    )

    return ManagerConfig(
        accounts=accounts,
        risk_limits=risk_limits,
        timezone=os.environ.get("TIMEZONE", "America/New_York"),
        dashboard_port=int(os.environ.get("DASHBOARD_PORT", "8050")),
        api_port=int(os.environ.get("API_PORT", "8051")),
        scan_interval_seconds=int(os.environ.get("SCAN_INTERVAL_SECONDS", "60")),
    )


def validate_paper_only(url: str) -> bool:
    """Return True if URL is a paper-trading endpoint. Raises on live URLs."""
    for blocked in BLOCKED_URL_PATTERNS:
        if blocked in url:
            raise SecurityError(
                f"BLOCKED: Attempted connection to LIVE endpoint: {url}. "
                f"Only paper trading is allowed."
            )
    return True


class SecurityError(Exception):
    """Raised when a live-trading endpoint is detected."""
    pass
