"""
Logging configuration: per-account logs + aggregated log.

Each account gets its own log file. All accounts also write to a combined log.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime


def setup_logging(log_dir: str = "logs") -> logging.Logger:
    """Set up the root logger with console + aggregated file output."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Avoid duplicate handlers on repeated calls
    if root.handlers:
        return root

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler (INFO level)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    root.addHandler(console)

    # Aggregated file (DEBUG level)
    agg_file = logging.FileHandler(
        log_path / f"manager_{date_str}.log", encoding="utf-8"
    )
    agg_file.setLevel(logging.DEBUG)
    agg_file.setFormatter(fmt)
    root.addHandler(agg_file)

    # Quiet noisy libraries
    for lib in ("urllib3", "alpaca", "werkzeug", "dash"):
        logging.getLogger(lib).setLevel(logging.WARNING)

    return root


def get_account_logger(account_name: str, log_dir: str = "logs") -> logging.Logger:
    """Get a logger specific to one account, with its own file handler."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    logger = logging.getLogger(f"manager.{account_name}")

    # Only add file handler once
    if not any(
        isinstance(h, logging.FileHandler)
        and account_name in getattr(h, "baseFilename", "")
        for h in logger.handlers
    ):
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        fh = logging.FileHandler(
            log_path / f"account_{account_name}_{date_str}.log",
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger
