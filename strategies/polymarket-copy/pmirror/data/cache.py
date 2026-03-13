"""
File-based caching layer for API responses.

Provides simple disk caching with TTL support to reduce redundant API calls.
"""

import hashlib
import json
import time
from datetime import timedelta
from pathlib import Path

from pydantic import BaseModel

from pmirror.config import get_settings


class CacheEntry(BaseModel):
    """A cached data entry with metadata."""

    key: str
    data: dict | list
    timestamp: float
    ttl_seconds: int

    @property
    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        if self.ttl_seconds == 0:
            return False  # No expiration
        return time.time() > (self.timestamp + self.ttl_seconds)

    @property
    def age_seconds(self) -> float:
        """Get the age of this cache entry in seconds."""
        return time.time() - self.timestamp


class FileCache:
    """
    Simple file-based cache with TTL support.

    Stores cached responses as JSON files on disk, organized by cache key.
    """

    def __init__(self, settings=None):
        """
        Initialize the file cache.

        Args:
            settings: Optional settings object (uses get_settings() if not provided)
        """
        config = settings if settings is not None else get_settings()
        self.cache_dir = config.cache.cache_dir
        self.default_ttl = config.cache.ttl_seconds
        self.enabled = config.cache.enabled

        # Create cache directory if it doesn't exist
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, key: str) -> Path:
        """
        Get the file path for a cache key.

        Args:
            key: Cache key

        Returns:
            Path to cache file
        """
        # Hash the key to get a safe filename
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        return self.cache_dir / f"{key_hash}.json"

    def _serialize_entry(self, entry: CacheEntry) -> str:
        """Serialize cache entry to JSON."""
        return entry.model_dump_json()

    def _deserialize_entry(self, data: str) -> CacheEntry:
        """Deserialize JSON to cache entry."""
        return CacheEntry.model_validate_json(data)

    def get(self, key: str) -> dict | list | None:
        """
        Get a value from cache.

        Args:
            key: Cache key

        Returns:
            Cached data, or None if not found or expired
        """
        if not self.enabled:
            return None

        cache_path = self._get_cache_path(key)

        if not cache_path.exists():
            return None

        try:
            with open(cache_path, "r") as f:
                entry = self._deserialize_entry(f.read())

            if entry.is_expired:
                # Remove expired file
                cache_path.unlink()
                return None

            return entry.data

        except (OSError, ValueError) as e:
            # Invalid cache file - remove it
            try:
                cache_path.unlink()
            except OSError:
                pass
            return None

    def set(
        self,
        key: str,
        data: dict | list,
        ttl: int | None = None,
    ) -> None:
        """
        Store a value in cache.

        Args:
            key: Cache key
            data: Data to cache
            ttl: Time-to-live in seconds (uses default if None)
        """
        if not self.enabled:
            return

        if ttl is None:
            ttl = self.default_ttl

        entry = CacheEntry(
            key=key,
            data=data,
            timestamp=time.time(),
            ttl_seconds=ttl,
        )

        cache_path = self._get_cache_path(key)

        try:
            with open(cache_path, "w") as f:
                f.write(self._serialize_entry(entry))
        except OSError:
            # Fail silently - cache is optional
            pass

    def delete(self, key: str) -> bool:
        """
        Delete a cache entry.

        Args:
            key: Cache key

        Returns:
            True if deleted, False if not found
        """
        cache_path = self._get_cache_path(key)

        if cache_path.exists():
            try:
                cache_path.unlink()
                return True
            except OSError:
                return False

        return False

    def clear(self) -> int:
        """
        Clear all cache entries.

        Returns:
            Number of cache files removed
        """
        if not self.enabled:
            return 0

        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
                count += 1
            except OSError:
                pass

        return count

    def get_size_bytes(self) -> int:
        """
        Get the total size of the cache in bytes.

        Returns:
            Size in bytes
        """
        if not self.enabled or not self.cache_dir.exists():
            return 0

        total = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                total += cache_file.stat().st_size
            except OSError:
                pass

        return total

    def get_entry_count(self) -> int:
        """
        Get the number of cached entries.

        Returns:
            Number of cache entries
        """
        if not self.enabled or not self.cache_dir.exists():
            return 0

        return len(list(self.cache_dir.glob("*.json")))

    def prune_expired(self) -> int:
        """
        Remove all expired cache entries.

        Returns:
            Number of entries removed
        """
        if not self.enabled:
            return 0

        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, "r") as f:
                    entry = self._deserialize_entry(f.read())

                if entry.is_expired:
                    cache_file.unlink()
                    count += 1
            except (OSError, ValueError):
                # Invalid file - remove it
                try:
                    cache_file.unlink()
                    count += 1
                except OSError:
                    pass

        return count

    def prune_by_size(self, max_bytes: int) -> int:
        """
        Remove oldest entries until cache size is below limit.

        Args:
            max_bytes: Maximum cache size in bytes

        Returns:
            Number of entries removed
        """
        if not self.enabled:
            return 0

        # Get all entries with their metadata
        entries = []
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, "r") as f:
                    entry = self._deserialize_entry(f.read())
                entries.append((entry, cache_file))
            except (OSError, ValueError):
                continue

        # Sort by timestamp (oldest first)
        entries.sort(key=lambda x: x[0].timestamp)

        # Remove entries until size is acceptable
        count = 0
        current_size = sum(e[0].data.model_dump_json().__sizeof__() for e in entries)

        for entry, cache_file in entries:
            if current_size <= max_bytes:
                break
            try:
                cache_file.unlink()
                current_size -= cache_file.stat().st_size
                count += 1
            except OSError:
                continue

        return count


def generate_cache_key(
    endpoint: str,
    params: dict | None = None,
) -> str:
    """
    Generate a cache key from endpoint and parameters.

    Args:
        endpoint: API endpoint path
        params: Query parameters

    Returns:
        Cache key string
    """
    parts = [endpoint]

    if params:
        # Sort params for consistent keys
        sorted_params = sorted(params.items())
        param_string = "&".join(f"{k}={v}" for k, v in sorted_params)
        parts.append(param_string)

    return ":".join(parts)


# Global cache instance
_cache: FileCache | None = None


def get_cache() -> FileCache:
    """
    Get the global cache instance (lazy initialization).

    Returns:
        FileCache instance
    """
    global _cache
    if _cache is None:
        _cache = FileCache()
    return _cache


def reset_cache() -> None:
    """Reset the global cache instance (useful for testing)."""
    global _cache
    _cache = None
