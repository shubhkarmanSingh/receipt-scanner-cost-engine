"""
logger.py — Structured logging configuration for the receipt scanner.

All modules should use: from logger import get_logger
                         logger = get_logger(__name__)
"""

import logging
import os


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for the given module name."""
    logger = logging.getLogger(name)

    if not logger.handlers:
        level = os.environ.get("LOG_LEVEL", "INFO").upper()
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        ))
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, level, logging.INFO))

    return logger
