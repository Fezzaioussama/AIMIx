"""Logging setup, applied once when the app starts (never at import time)."""

from __future__ import annotations

import logging.config

QUIET_LIBRARIES = ("httpx", "mcp")


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
            # Both log every request's URL and MCP session id at INFO. Users choose
            # those URLs (page fetches, their own MCP servers) and some carry a
            # token, so only their warnings are kept (AGENTS.md §6).
            "loggers": {name: {"level": "WARNING"} for name in QUIET_LIBRARIES},
        }
    )
