"""
Tests for pmirror configuration settings.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from pmirror.config import (
    ApiConfig,
    BacktestConfig,
    CacheConfig,
    DataConfig,
    Settings,
    get_settings,
    reload_settings,
)


class TestApiConfig:
    """Tests for ApiConfig."""

    def test_default_values(self):
        """ApiConfig should have correct default values."""
        config = ApiConfig()
        assert config.data_api_url == "https://data-api.polymarket.com"
        assert config.gamma_api_url == "https://gamma-api.polymarket.com"
        assert config.request_timeout == 30
        assert config.max_retries == 3
        assert config.retry_delay == 1.0
        assert config.rate_limit_delay == 0.1

    def test_request_timeout_validation(self):
        """Request timeout should be within valid range."""
        with pytest.raises(ValidationError):
            ApiConfig(request_timeout=0)

        with pytest.raises(ValidationError):
            ApiConfig(request_timeout=400)

        # Valid values should work
        config = ApiConfig(request_timeout=60)
        assert config.request_timeout == 60

    def test_max_retries_validation(self):
        """Max retries should be within valid range."""
        with pytest.raises(ValidationError):
            ApiConfig(max_retries=-1)

        with pytest.raises(ValidationError):
            ApiConfig(max_retries=20)

        # Valid values should work
        config = ApiConfig(max_retries=5)
        assert config.max_retries == 5

    def test_rate_limit_delay_allows_zero(self):
        """Rate limit delay should allow zero (no delay)."""
        config = ApiConfig(rate_limit_delay=0.0)
        assert config.rate_limit_delay == 0.0

    def test_env_prefix(self):
        """Environment variables with POLY_API_ prefix should override defaults."""
        with patch.dict(os.environ, {"POLY_API_REQUEST_TIMEOUT": "60"}):
            config = ApiConfig()
            assert config.request_timeout == 60


class TestCacheConfig:
    """Tests for CacheConfig."""

    def test_default_values(self):
        """CacheConfig should have correct default values."""
        config = CacheConfig()
        assert config.enabled is True
        assert config.ttl_seconds == 300
        assert config.max_size_mb == 100
        assert config.cache_dir == Path.home() / ".cache" / "pmirror"

    def test_ttl_allows_zero(self):
        """TTL of 0 should be valid (no expiration)."""
        config = CacheConfig(ttl_seconds=0)
        assert config.ttl_seconds == 0

    def test_max_size_validation(self):
        """Max size should be within valid range."""
        with pytest.raises(ValidationError):
            CacheConfig(max_size_mb=0)

        with pytest.raises(ValidationError):
            CacheConfig(max_size_mb=20000)

    def test_cache_dir_defaults_to_home(self):
        """Cache dir should default to ~/.cache/pmirror."""
        config = CacheConfig()
        expected = Path.home() / ".cache" / "pmirror"
        assert config.cache_dir == expected


class TestDataConfig:
    """Tests for DataConfig."""

    def test_default_values(self):
        """DataConfig should have correct default values."""
        config = DataConfig()
        assert config.data_root == Path("data")
        assert config.raw_data_dir == Path("data/raw")
        assert config.clean_data_dir == Path("data/clean")
        assert config.default_file_format == "parquet"

    def test_relative_paths_resolve_correctly(self):
        """Relative paths should resolve correctly against data_root."""
        config = DataConfig(data_root=Path("/mnt/data"))
        # Fields are independent - data_root doesn't affect raw/clean dirs unless explicitly set
        assert config.data_root == Path("/mnt/data")
        # raw_data_dir and clean_data_dir keep their default values unless overridden
        assert config.raw_data_dir == Path("data/raw")
        assert config.clean_data_dir == Path("data/clean")

    def test_explicit_raw_data_dir_resolves(self):
        """Explicitly set raw_data_dir should be respected."""
        config = DataConfig(
            data_root=Path("/mnt/data"),
            raw_data_dir=Path("/mnt/data/custom/raw"),
        )
        assert config.raw_data_dir == Path("/mnt/data/custom/raw")

    def test_absolute_paths_preserved(self):
        """Absolute paths should be preserved."""
        config = DataConfig(
            raw_data_dir=Path("/absolute/path/raw"),
            clean_data_dir=Path("/absolute/path/clean"),
        )
        assert config.raw_data_dir == Path("/absolute/path/raw")
        assert config.clean_data_dir == Path("/absolute/path/clean")


class TestBacktestConfig:
    """Tests for BacktestConfig."""

    def test_default_values(self):
        """BacktestConfig should have correct default values."""
        config = BacktestConfig()
        assert config.default_capital == 1000.0
        assert config.default_policy == "mirror_latency"
        assert config.commission_rate == 0.0
        assert config.slippage_bps == 0

    def test_capital_must_be_positive(self):
        """Capital must be greater than zero."""
        with pytest.raises(ValidationError):
            BacktestConfig(default_capital=0)

        with pytest.raises(ValidationError):
            BacktestConfig(default_capital=-100)

    def test_commission_rate_validation(self):
        """Commission rate should be between 0 and 10%."""
        with pytest.raises(ValidationError):
            BacktestConfig(commission_rate=-0.01)

        with pytest.raises(ValidationError):
            BacktestConfig(commission_rate=0.15)

        # Valid values
        config = BacktestConfig(commission_rate=0.05)  # 5%
        assert config.commission_rate == 0.05

    def test_slippage_bps_validation(self):
        """Slippage should be between 0 and 100 basis points."""
        with pytest.raises(ValidationError):
            BacktestConfig(slippage_bps=-5)

        with pytest.raises(ValidationError):
            BacktestConfig(slippage_bps=150)

        # Valid values
        config = BacktestConfig(slippage_bps=50)  # 0.5%
        assert config.slippage_bps == 50


class TestSettings:
    """Tests for main Settings class."""

    def test_default_settings(self):
        """Settings should load with all defaults."""
        settings = Settings()
        assert settings.api.data_api_url == "https://data-api.polymarket.com"
        assert settings.cache.enabled is True
        assert settings.backtest.default_capital == 1000.0
        assert settings.reports_dir == Path("reports")
        assert settings.debug is False
        assert settings.log_level == "INFO"

    def test_log_level_normalized(self):
        """Log level should be normalized to uppercase."""
        settings = Settings(log_level="debug")
        assert settings.log_level == "DEBUG"

        settings = Settings(log_level="WaRNiNg")
        assert settings.log_level == "WARNING"

    def test_nested_env_vars(self):
        """Nested environment variables should work."""
        with patch.dict(os.environ, {"POLY_API__REQUEST_TIMEOUT": "90"}):
            settings = Settings()
            assert settings.api.request_timeout == 90

    def test_env_var_override(self):
        """Top-level environment variables should override defaults."""
        with patch.dict(os.environ, {"POLY_DEBUG": "true"}):
            settings = Settings()
            assert settings.debug is True

        with patch.dict(os.environ, {"POLY_LOG_LEVEL": "DEBUG"}):
            settings = Settings()
            assert settings.log_level == "DEBUG"

    def test_ensure_directories(self, tmp_path):
        """ensure_directories should create all required directories."""
        settings = Settings(
            cache=CacheConfig(cache_dir=tmp_path / "cache"),
            data=DataConfig(
                data_root=tmp_path / "data",
                raw_data_dir=tmp_path / "data" / "raw",
                clean_data_dir=tmp_path / "data" / "clean",
            ),
            reports_dir=tmp_path / "reports",
        )

        settings.ensure_directories()

        assert (tmp_path / "cache").exists()
        assert (tmp_path / "data").exists()
        assert (tmp_path / "data" / "raw").exists()
        assert (tmp_path / "data" / "clean").exists()
        assert (tmp_path / "reports").exists()


class TestSettingsCache:
    """Tests for settings caching."""

    def test_get_settings_is_cached(self):
        """get_settings should return the same instance on subsequent calls."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_reload_settings_clears_cache(self):
        """reload_settings should return a new instance."""
        settings1 = get_settings()
        settings2 = reload_settings()
        assert settings1 is not settings2

    def test_reload_with_new_env(self):
        """reload should pick up new environment variables."""
        settings1 = get_settings()

        with patch.dict(os.environ, {"POLY_DEBUG": "true"}):
            settings2 = reload_settings()
            assert settings2.debug is True

        # Original instance should be unchanged
        assert settings1.debug is False
