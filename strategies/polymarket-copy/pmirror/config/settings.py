"""
Configuration settings for pmirror using Pydantic Settings.

Settings are loaded from environment variables with sensible defaults.
Prefix environment variables with POLY_ to override:

    export POLY_API_URL=https://custom-api.com
    export POLY_CACHE_TTL=300
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiConfig(BaseSettings):
    """Configuration for Polymarket API endpoints."""

    data_api_url: str = Field(
        default="https://data-api.polymarket.com",
        description="Base URL for Polymarket Data API",
    )

    gamma_api_url: str = Field(
        default="https://gamma-api.polymarket.com",
        description="Base URL for Polymarket Gamma API",
    )

    request_timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Request timeout in seconds",
    )

    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum number of retries for failed requests",
    )

    retry_delay: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        description="Initial retry delay in seconds (exponential backoff)",
    )

    rate_limit_delay: float = Field(
        default=0.1,
        ge=0.0,
        le=5.0,
        description="Delay between requests to respect rate limits",
    )

    model_config = SettingsConfigDict(env_prefix="POLY_API_")


class CacheConfig(BaseSettings):
    """Configuration for data caching."""

    enabled: bool = Field(
        default=True,
        description="Enable/disable caching",
    )

    ttl_seconds: int = Field(
        default=300,
        ge=0,
        description="Cache time-to-live in seconds (0 = no expiration)",
    )

    max_size_mb: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Maximum cache size in megabytes",
    )

    cache_dir: Path = Field(
        default=Path.home() / ".cache" / "pmirror",
        description="Directory for cache storage",
    )

    model_config = SettingsConfigDict(env_prefix="POLY_CACHE_")


class DataConfig(BaseSettings):
    """Configuration for data storage paths."""

    data_root: Path = Field(
        default=Path("data"),
        description="Root directory for all data files",
    )

    raw_data_dir: Path = Field(
        default=Path("data/raw"),
        description="Directory for raw fetched data",
    )

    clean_data_dir: Path = Field(
        default=Path("data/clean"),
        description="Directory for normalized/cleaned data",
    )

    default_file_format: str = Field(
        default="parquet",
        description="Default file format for data storage",
    )

    model_config = SettingsConfigDict(env_prefix="POLY_DATA_")

    @field_validator("raw_data_dir", "clean_data_dir", mode="before")
    @classmethod
    def resolve_relative_paths(cls, v: Path, info) -> Path:
        """Resolve relative paths against data_root."""
        if isinstance(v, str):
            v = Path(v)
        if not v.is_absolute():
            # Get data_root from the field values if available
            data_root = info.data.get("data_root", Path("data"))
            if isinstance(data_root, str):
                data_root = Path(data_root)
            return data_root / v.name if v.name == v.as_posix() else v
        return v


class BacktestConfig(BaseSettings):
    """Configuration for backtest execution."""

    default_capital: float = Field(
        default=1000.0,
        gt=0,
        description="Default starting capital for backtests",
    )

    default_policy: str = Field(
        default="mirror_latency",
        description="Default copy policy to use",
    )

    commission_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=0.1,
        description="Commission rate per trade (0.0 = none, 0.01 = 1%)",
    )

    slippage_bps: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Slippage in basis points (100 bps = 1%)",
    )

    model_config = SettingsConfigDict(env_prefix="POLY_BACKTEST_")


class Settings(BaseSettings):
    """
    Main settings class for pmirror.

    Environment variables:
        POLY_API_DATA_API_URL      - Override Data API URL
        POLY_API_REQUEST_TIMEOUT   - Request timeout in seconds
        POLY_CACHE_ENABLED         - Enable/disable caching (true/false)
        POLY_CACHE_TTL_SECONDS     - Cache TTL in seconds
        POLY_DATA_DATA_ROOT        - Root data directory path
        POLY_REPORTS_DIR           - Reports directory path
        POLY_BACKTEST_DEFAULT_CAPITAL - Default starting capital

    Example .env file:
        POLY_API_REQUEST_TIMEOUT=60
        POLY_CACHE_TTL_SECONDS=600
        POLY_DATA_DATA_ROOT=/mnt/data/pmirror
    """

    api: ApiConfig = Field(default_factory=ApiConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)

    reports_dir: Path = Field(
        default=Path("reports"),
        description="Directory for generated reports",
    )

    debug: bool = Field(
        default=False,
        description="Enable debug mode (verbose logging)",
    )

    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )

    model_config = SettingsConfigDict(
        env_prefix="POLY_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, v: str) -> str:
        """Normalize log level to uppercase."""
        return v.upper()

    def ensure_directories(self) -> None:
        """Create all required directories if they don't exist."""
        self.cache.cache_dir.mkdir(parents=True, exist_ok=True)
        self.data.data_root.mkdir(parents=True, exist_ok=True)
        self.data.raw_data_dir.mkdir(parents=True, exist_ok=True)
        self.data.clean_data_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses LRU cache to ensure settings are loaded only once per process.
    Environment changes will not take effect until process restart.
    """
    return Settings()


def reload_settings() -> Settings:
    """
    Reload settings, bypassing cache.

    Use this when you need to pick up environment variable changes
    within the same process (e.g., in tests).
    """
    get_settings.cache_clear()
    return get_settings()
