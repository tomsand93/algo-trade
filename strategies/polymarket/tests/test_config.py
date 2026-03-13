"""Tests for Settings configuration loading."""
import os
import pytest
from pydantic import ValidationError


class TestSettings:
    """Settings: defaults, .env override, secret redaction."""

    def test_default_values(self, monkeypatch):
        """Settings loads with correct defaults when no .env overrides exist."""
        # Clear any env vars that might be set in the test environment
        for key in ["Z_ENTRY_THRESHOLD", "ROLLING_WINDOW", "LOG_LEVEL", "MAX_POSITION_SIZE"]:
            monkeypatch.delenv(key, raising=False)

        from polymarket_bot.config import Settings
        # Force re-read with no env file by pointing at a non-existent path
        s = Settings(_env_file=".env.nonexistent")

        assert s.log_level == "INFO"
        assert s.rolling_window == 20
        assert s.z_entry_threshold == 2.0
        assert s.z_exit_threshold == 0.5
        assert s.max_position_size == 10.0
        assert s.daily_loss_limit == 50.0
        assert s.snapshot_dir == "data/snapshots"

    def test_env_var_override(self, monkeypatch):
        """Environment variables override defaults."""
        monkeypatch.setenv("Z_ENTRY_THRESHOLD", "3.0")
        monkeypatch.setenv("ROLLING_WINDOW", "30")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        from polymarket_bot.config import Settings
        s = Settings(_env_file=".env.nonexistent")

        assert s.z_entry_threshold == 3.0
        assert s.rolling_window == 30
        assert s.log_level == "DEBUG"

    def test_secret_not_in_repr(self, monkeypatch):
        """API keys are never exposed in repr or str output."""
        monkeypatch.setenv("POLYMARKET_API_KEY", "super-secret-key-12345")

        from polymarket_bot.config import Settings
        s = Settings(_env_file=".env.nonexistent")

        output = repr(s) + str(s)
        assert "super-secret-key-12345" not in output, "Secret key leaked in repr/str!"

    def test_invalid_z_entry_rejected(self, monkeypatch):
        """z_entry_threshold must be > 0."""
        monkeypatch.setenv("Z_ENTRY_THRESHOLD", "0")

        from polymarket_bot.config import Settings
        with pytest.raises(ValidationError):
            Settings(_env_file=".env.nonexistent")

    def test_invalid_rolling_window_rejected(self, monkeypatch):
        """rolling_window must be > 2."""
        monkeypatch.setenv("ROLLING_WINDOW", "2")

        from polymarket_bot.config import Settings
        with pytest.raises(ValidationError):
            Settings(_env_file=".env.nonexistent")

    def test_load_settings_returns_settings_instance(self):
        """load_settings() returns a Settings object."""
        from polymarket_bot.config import load_settings, Settings
        s = load_settings()
        assert isinstance(s, Settings)

    def test_api_key_get_secret_value(self, monkeypatch):
        """SecretStr fields expose value only via .get_secret_value()."""
        monkeypatch.setenv("POLYMARKET_API_KEY", "test-key-abc")

        from polymarket_bot.config import Settings
        s = Settings(_env_file=".env.nonexistent")

        # .get_secret_value() returns the actual value
        assert s.polymarket_api_key.get_secret_value() == "test-key-abc"

    def test_stop_loss_pct_default(self):
        from polymarket_bot.config import Settings
        s = Settings(_env_file=".env.nonexistent")
        assert s.stop_loss_pct == 0.20

    def test_cooldown_seconds_default(self):
        from polymarket_bot.config import Settings
        s = Settings(_env_file=".env.nonexistent")
        assert s.cooldown_seconds == 300

    def test_initial_capital_default(self):
        from polymarket_bot.config import Settings
        s = Settings(_env_file=".env.nonexistent")
        assert s.initial_capital == 100.0

    def test_stop_loss_pct_env_override(self, monkeypatch):
        monkeypatch.setenv("STOP_LOSS_PCT", "0.10")
        from polymarket_bot.config import Settings
        s = Settings(_env_file=".env.nonexistent")
        assert s.stop_loss_pct == 0.10

    def test_cooldown_seconds_env_override(self, monkeypatch):
        monkeypatch.setenv("COOLDOWN_SECONDS", "60")
        from polymarket_bot.config import Settings
        s = Settings(_env_file=".env.nonexistent")
        assert s.cooldown_seconds == 60

    def test_initial_capital_env_override(self, monkeypatch):
        monkeypatch.setenv("INITIAL_CAPITAL", "500.0")
        from polymarket_bot.config import Settings
        s = Settings(_env_file=".env.nonexistent")
        assert s.initial_capital == 500.0


class TestSettingsPhase4Fields:
    def test_polymarket_private_key_default_is_empty_secret(self):
        from polymarket_bot.config import Settings
        s = Settings()
        assert s.polymarket_private_key.get_secret_value() == ""

    def test_polymarket_api_passphrase_default_is_empty_secret(self):
        from polymarket_bot.config import Settings
        s = Settings()
        assert s.polymarket_api_passphrase.get_secret_value() == ""

    def test_poll_interval_seconds_default_is_60(self):
        from polymarket_bot.config import Settings
        s = Settings()
        assert s.poll_interval_seconds == 60

    def test_state_file_default(self):
        from polymarket_bot.config import Settings
        s = Settings()
        assert s.state_file == "data/state/positions.json"

    def test_signature_type_default_is_0(self):
        from polymarket_bot.config import Settings
        s = Settings()
        assert s.signature_type == 0

    def test_poll_interval_seconds_must_be_positive(self):
        from polymarket_bot.config import Settings
        with pytest.raises(Exception):
            Settings(poll_interval_seconds=0)

    def test_private_key_loaded_from_env(self, monkeypatch):
        monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0xdeadbeef")
        from polymarket_bot.config import Settings
        s = Settings()
        assert s.polymarket_private_key.get_secret_value() == "0xdeadbeef"

    def test_passphrase_loaded_from_env(self, monkeypatch):
        monkeypatch.setenv("POLYMARKET_API_PASSPHRASE", "mysecretpass")
        from polymarket_bot.config import Settings
        s = Settings()
        assert s.polymarket_api_passphrase.get_secret_value() == "mysecretpass"
