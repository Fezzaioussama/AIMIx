"""Logging setup, applied once when the app starts (never at import time)."""

from __future__ import annotations

import logging
import logging.config
import re

QUIET_LIBRARIES = ("httpx", "mcp")
#: A webhook's link is its credential (api/endpoints/webhooks.py, /api/hooks/<token>).
WEBHOOK_TOKEN = re.compile(r"(/api/hooks/)[^/?#\s]+")


class WebhookTokenFilter(logging.Filter):
    """Keeps webhook tokens out of the access log: the path it prints is the link
    another app calls, so the token is replaced before the line is written."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                WEBHOOK_TOKEN.sub(r"\1<token>", arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True


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
    # Added to uvicorn's own access logger (configuring it above would drop its
    # handler), once however many apps this process creates.
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, WebhookTokenFilter) for item in access.filters):
        access.addFilter(WebhookTokenFilter())
