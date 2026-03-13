"""
Tests for file-based cache layer.
"""

import json
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from pmirror.data import FileCache, CacheEntry, generate_cache_key, get_cache, reset_cache


class TestCacheEntry:
    """Tests for CacheEntry model."""

    def test_create_entry(self):
        """Should create cache entry with metadata."""
        entry = CacheEntry(
            key="test-key",
            data={"value": 123},
            timestamp=time.time(),
            ttl_seconds=300,
        )
        assert entry.key == "test-key"
        assert entry.data["value"] == 123

    def test_is_expired_false(self):
        """Should not be expired when within TTL."""
        entry = CacheEntry(
            key="test",
            data={},
            timestamp=time.time(),
            ttl_seconds=300,
        )
        assert entry.is_expired is False

    def test_is_expired_true(self):
        """Should be expired when TTL passed."""
        entry = CacheEntry(
            key="test",
            data={},
            timestamp=time.time() - 400,
            ttl_seconds=300,
        )
        assert entry.is_expired is True

    def test_no_expiration_when_ttl_zero(self):
        """Should not expire when TTL is 0."""
        entry = CacheEntry(
            key="test",
            data={},
            timestamp=time.time() - 999999,
            ttl_seconds=0,
        )
        assert entry.is_expired is False

    def test_age_seconds(self):
        """Should calculate correct age."""
        now = time.time()
        entry = CacheEntry(
            key="test",
            data={},
            timestamp=now - 100,
            ttl_seconds=300,
        )
        assert abs(entry.age_seconds - 100) < 1  # Allow 1s tolerance


class TestFileCache:
    """Tests for FileCache."""

    def test_create_cache(self, tmp_path):
        """Should create cache directory."""
        with patch("pmirror.data.cache.get_settings") as mock_settings:
            config = Mock()
            config.cache.cache_dir = tmp_path / "cache"
            config.cache.enabled = True
            config.cache.ttl_seconds = 300
            mock_settings.return_value = config

            cache = FileCache()
            assert cache.cache_dir == tmp_path / "cache"
            assert cache.cache_dir.exists()

    def test_set_and_get(self, tmp_path):
        """Should store and retrieve values."""
        with patch("pmirror.data.cache.get_settings") as mock_settings:
            config = Mock()
            config.cache.cache_dir = tmp_path / "cache"
            config.cache.enabled = True
            config.cache.ttl_seconds = 300
            mock_settings.return_value = config

            cache = FileCache()
            cache.set("test-key", {"data": "value"})

            result = cache.get("test-key")
            assert result == {"data": "value"}

    def test_get_returns_none_for_missing(self, tmp_path):
        """Should return None for missing keys."""
        with patch("pmirror.data.cache.get_settings") as mock_settings:
            config = Mock()
            config.cache.cache_dir = tmp_path / "cache"
            config.cache.enabled = True
            config.cache.ttl_seconds = 300
            mock_settings.return_value = config

            cache = FileCache()
            result = cache.get("nonexistent")
            assert result is None

    def test_get_returns_none_for_expired(self, tmp_path):
        """Should return None for expired entries."""
        with patch("pmirror.data.cache.get_settings") as mock_settings:
            config = Mock()
            config.cache.cache_dir = tmp_path / "cache"
            config.cache.enabled = True
            config.cache.ttl_seconds = 1
            mock_settings.return_value = config

            cache = FileCache()
            cache.set("test", {"value": 1})

            # Wait for expiration
            time.sleep(1.1)

            result = cache.get("test")
            assert result is None

            # File should be deleted
            cache_path = cache._get_cache_path("test")
            assert not cache_path.exists()

    def test_custom_ttl(self, tmp_path):
        """Should use custom TTL when provided."""
        with patch("pmirror.data.cache.get_settings") as mock_settings:
            config = Mock()
            config.cache.cache_dir = tmp_path / "cache"
            config.cache.enabled = True
            config.cache.ttl_seconds = 300
            mock_settings.return_value = config

            cache = FileCache()
            cache.set("test", {"data": 1}, ttl=10)

            entry_path = cache._get_cache_path("test")
            with open(entry_path) as f:
                entry = CacheEntry.model_validate_json(f.read())

            assert entry.ttl_seconds == 10

    def test_delete_existing(self, tmp_path):
        """Should delete existing entries."""
        with patch("pmirror.data.cache.get_settings") as mock_settings:
            config = Mock()
            config.cache.cache_dir = tmp_path / "cache"
            config.cache.enabled = True
            config.cache.ttl_seconds = 300
            mock_settings.return_value = config

            cache = FileCache()
            cache.set("test", {"data": 1})

            assert cache.delete("test") is True
            assert cache.get("test") is None

    def test_delete_nonexistent(self, tmp_path):
        """Should return False when deleting nonexistent key."""
        with patch("pmirror.data.cache.get_settings") as mock_settings:
            config = Mock()
            config.cache.cache_dir = tmp_path / "cache"
            config.cache.enabled = True
            config.cache.ttl_seconds = 300
            mock_settings.return_value = config

            cache = FileCache()
            assert cache.delete("nonexistent") is False

    def test_clear(self, tmp_path):
        """Should clear all cache entries."""
        with patch("pmirror.data.cache.get_settings") as mock_settings:
            config = Mock()
            config.cache.cache_dir = tmp_path / "cache"
            config.cache.enabled = True
            config.cache.ttl_seconds = 300
            mock_settings.return_value = config

            cache = FileCache()
            cache.set("key1", {"data": 1})
            cache.set("key2", {"data": 2})
            cache.set("key3", {"data": 3})

            count = cache.clear()
            assert count == 3
            assert cache.get_entry_count() == 0

    def test_clear_when_disabled(self, tmp_path):
        """Should do nothing when cache is disabled."""
        with patch("pmirror.data.cache.get_settings") as mock_settings:
            config = Mock()
            config.cache.cache_dir = tmp_path / "cache"
            config.cache.enabled = False
            config.cache.ttl_seconds = 300
            mock_settings.return_value = config

            cache = FileCache()
            count = cache.clear()
            assert count == 0

    def test_get_size_bytes(self, tmp_path):
        """Should calculate total cache size."""
        with patch("pmirror.data.cache.get_settings") as mock_settings:
            config = Mock()
            config.cache.cache_dir = tmp_path / "cache"
            config.cache.enabled = True
            config.cache.ttl_seconds = 300
            mock_settings.return_value = config

            cache = FileCache()
            cache.set("key1", {"data": "x" * 100})

            size = cache.get_size_bytes()
            assert size > 0

    def test_get_entry_count(self, tmp_path):
        """Should return number of cache entries."""
        with patch("pmirror.data.cache.get_settings") as mock_settings:
            config = Mock()
            config.cache.cache_dir = tmp_path / "cache"
            config.cache.enabled = True
            config.cache.ttl_seconds = 300
            mock_settings.return_value = config

            cache = FileCache()
            assert cache.get_entry_count() == 0

            cache.set("key1", {"data": 1})
            assert cache.get_entry_count() == 1

            cache.set("key2", {"data": 2})
            assert cache.get_entry_count() == 2

    def test_prune_expired(self, tmp_path):
        """Should remove expired entries."""
        with patch("pmirror.data.cache.get_settings") as mock_settings:
            config = Mock()
            config.cache.cache_dir = tmp_path / "cache"
            config.cache.enabled = True
            config.cache.ttl_seconds = 1
            mock_settings.return_value = config

            cache = FileCache()
            cache.set("expired1", {"data": 1})
            cache.set("expired2", {"data": 2})

            time.sleep(1.1)

            cache.set("fresh", {"data": 3}, ttl=1000)

            count = cache.prune_expired()
            assert count == 2
            assert cache.get_entry_count() == 1

    def test_disabled_cache_no_ops(self, tmp_path):
        """Should not perform operations when disabled."""
        with patch("pmirror.data.cache.get_settings") as mock_settings:
            config = Mock()
            config.cache.cache_dir = tmp_path / "cache"
            config.cache.enabled = False
            config.cache.ttl_seconds = 300
            mock_settings.return_value = config

            cache = FileCache()

            # Set should do nothing
            cache.set("test", {"data": 1})

            # Get should return None
            assert cache.get("test") is None

            # Cache directory should not be created
            assert not cache.cache_dir.exists()

    def test_stores_list_data(self, tmp_path):
        """Should correctly cache list data."""
        with patch("pmirror.data.cache.get_settings") as mock_settings:
            config = Mock()
            config.cache.cache_dir = tmp_path / "cache"
            config.cache.enabled = True
            config.cache.ttl_seconds = 300
            mock_settings.return_value = config

            cache = FileCache()
            data = [{"id": 1}, {"id": 2}, {"id": 3}]
            cache.set("list-key", data)

            result = cache.get("list-key")
            assert result == data

    def test_handles_corrupt_cache_files(self, tmp_path):
        """Should handle corrupt cache files gracefully."""
        with patch("pmirror.data.cache.get_settings") as mock_settings:
            config = Mock()
            config.cache.cache_dir = tmp_path / "cache"
            config.cache.enabled = True
            config.cache.ttl_seconds = 300
            mock_settings.return_value = config

            cache = FileCache()

            # Create a corrupt cache file
            cache_path = cache._get_cache_path("corrupt")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w") as f:
                f.write("invalid json {{{")

            # Should return None and delete the file
            result = cache.get("corrupt")
            assert result is None
            assert not cache_path.exists()


class TestGenerateCacheKey:
    """Tests for cache key generation."""

    def test_key_without_params(self):
        """Should generate key from endpoint only."""
        key = generate_cache_key("/markets")
        assert key == "/markets"

    def test_key_with_params(self):
        """Should include params in key."""
        key = generate_cache_key("/trades", {"limit": 10, "maker": "0xabc"})
        # Params should be sorted
        assert "limit=10" in key
        assert "maker=0xabc" in key
        assert ":" in key

    def test_params_are_sorted(self):
        """Should sort params for consistent keys."""
        key1 = generate_cache_key("/test", {"b": 2, "a": 1})
        key2 = generate_cache_key("/test", {"a": 1, "b": 2})
        assert key1 == key2


class TestGlobalCache:
    """Tests for global cache instance."""

    def test_get_cache_singleton(self, tmp_path):
        """Should return singleton cache instance."""
        with patch("pmirror.data.cache.get_settings") as mock_settings:
            config = Mock()
            config.cache.cache_dir = tmp_path / "cache"
            config.cache.enabled = True
            config.cache.ttl_seconds = 300
            mock_settings.return_value = config

            cache1 = get_cache()
            cache2 = get_cache()
            assert cache1 is cache2

    def test_reset_cache(self, tmp_path):
        """Should reset global cache instance."""
        with patch("pmirror.data.cache.get_settings") as mock_settings:
            config = Mock()
            config.cache.cache_dir = tmp_path / "cache"
            config.cache.enabled = True
            config.cache.ttl_seconds = 300
            mock_settings.return_value = config

            cache1 = get_cache()
            reset_cache()
            cache2 = get_cache()

            # Should be different instances
            assert cache1 is not cache2
