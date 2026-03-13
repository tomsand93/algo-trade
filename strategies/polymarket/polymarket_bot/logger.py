"""Loguru logger setup. Call setup_logger() once at startup in run.py."""
import sys
from loguru import logger


def setup_logger(level: str = "INFO") -> None:
    """Remove default handler and add custom-formatted stderr handler."""
    logger.remove()  # Remove loguru's default handler (prevents duplicate output)
    logger.add(
        sys.stderr,
        level=level,
        format="[{time:YYYY-MM-DD HH:mm:ss}] {level}: {message}",
        colorize=True,
    )


# Re-export logger so other modules can: from polymarket_bot.logger import logger
__all__ = ["setup_logger", "logger"]
