"""Logging setup, applied once when the app starts (never at import time)."""

from __future__ import annotations

import logging
import logging.config

QUIET_LIBRARIES = ("httpx", "mcp")


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
            # httpx and mcp log every request's URL and MCP session id at INFO. Users
            # choose those URLs (page fetches, their own MCP servers) and some carry a
            # token, so only their warnings are kept. The E2B SDK logs the code it
            # submits at DEBUG, and agent-written code can embed user data, so it
            # never logs below INFO (AGENTS.md §6).
            "loggers": {
                **{name: {"level": "WARNING"} for name in QUIET_LIBRARIES},
                "e2b_code_interpreter": {"level": _at_least_info(level)},
            },
        }
    )
