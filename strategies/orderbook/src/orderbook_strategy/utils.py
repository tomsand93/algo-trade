"""Utility functions."""

import logging
from typing import Any


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Set up logging configuration."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    return logging.getLogger(__name__)


def deep_getattr(obj: Any, path: str, default=None):
    """Get nested attribute using dot notation."""
    try:
        parts = path.split(".")
        current = obj
        for part in parts:
            current = getattr(current, part)
        return current
    except (AttributeError, KeyError):
        return default
