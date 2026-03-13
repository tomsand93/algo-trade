"""Configuration loading from .env file via pydantic-settings."""
import os
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignore unrecognised .env keys
    )

    # Secrets — pydantic hides value in repr automatically
    polymarket_api_key: SecretStr = Field(default="")
    polymarket_api_secret: SecretStr = Field(default="")

    # Phase 4: Live trading auth (leave empty for paper mode)
    polymarket_private_key: SecretStr = Field(default="")
    polymarket_api_passphrase: SecretStr = Field(default="")

    # Phase 4: Operational
    poll_interval_seconds: int = Field(default=60, gt=0)
    state_file: str = Field(default="data/state/positions.json")
    signature_type: int = Field(default=0)

    # Strategy parameters
    z_entry_threshold: float = Field(default=2.0, gt=0)
    z_exit_threshold: float = Field(default=0.5, ge=0)
    rolling_window: int = Field(default=20, gt=2)

    # Risk limits (USD)
    max_position_size: float = Field(default=10.0, gt=0)
    daily_loss_limit: float = Field(default=50.0, gt=0)

    # Risk: per-trade stop-loss and re-entry cooldown
    stop_loss_pct: float = Field(default=0.20, gt=0, le=1.0)
    # 20% loss on entry price triggers stop. For YES token bought at 0.50,
    # stop fires at 0.40. Adjust in .env for tighter/looser control.

    cooldown_seconds: int = Field(default=300, gt=0)
    # 5-minute cooldown after each trade per market. Prevents rapid re-entry.

    # Portfolio tracking baseline
    initial_capital: float = Field(default=100.0, gt=0)
    # Starting portfolio value for drawdown and PnL calculations.
    # For a real <$1K account, set to actual balance in .env.

    # Operational
    snapshot_dir: str = Field(default="data/snapshots")
    log_level: str = Field(default="INFO")


def load_settings() -> Settings:
    """Load and return settings. Warns if .env file is missing."""
    if not os.path.exists(".env"):
        import warnings
        warnings.warn(
            ".env file not found — using defaults. Copy .env.example to .env to configure.",
            stacklevel=2,
        )
    return Settings()
