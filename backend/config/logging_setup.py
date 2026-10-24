"""Logging setup, applied once when the app starts (never at import time)."""

from __future__ import annotations

import logging
import logging.config


def _at_least_info(level: str) -> str:
    numeric = logging.getLevelName(level)
    return level if isinstance(numeric, int) and numeric >= logging.INFO else "INFO"


def configure_logging(level: str) -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
            },
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "standard"},
            },
            "root": {"handlers": ["console"], "level": level},
            # The E2B SDK logs the code it submits at DEBUG, and agent-written
            # code can embed user data, so it never logs below INFO (§6).
            "loggers": {"e2b_code_interpreter": {"level": _at_least_info(level)}},
        }
    )
