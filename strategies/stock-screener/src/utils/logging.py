"""Logging configuration for screener."""

import logging
import sys
from pathlib import Path
from datetime import datetime


def setup_logging(log_dir: str = "results", level: int = logging.INFO) -> logging.Logger:
    """Setup logging to both file and console."""
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d")
    log_file = log_path / f"run_{timestamp}.log"

    # Configure root logger
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

    return logging.getLogger("screener")


def log_runtime(func):
    """Decorator to log function runtime."""
    import time
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = logging.getLogger("screener")
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        logger.info(f"{func.__name__} completed in {elapsed:.2f}s")
        return result
    return wrapper
