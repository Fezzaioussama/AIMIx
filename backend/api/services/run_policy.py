"""What the server allows every pipeline run, read once from settings (AGENTS.md §6).

``RunService`` applies it on every path that starts or resumes a run (the Runs
screen, the compatibility endpoint, schedules, chat's ``run_pipeline`` tool):
the spending limits (``RunLimits``), how many runs one account may have active,
how long a caller that waits for a run's end waits at most, the free disk
space a run must leave (a run's inputs and outputs grow the database), where
a run's result goes once it has ended (result deliveries), and who tells its
owner (notifications).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from api.db import Database
from api.security import secret_box_for
from api.services.deliveries.sender import ResultDeliveries, send_policy
from api.services.files.disk import DiskReserve, disk_reserve
from api.services.notifications import notifier
from api.services.run_budget import NO_LIMITS, RunLimits, run_limits
from config.settings import Settings

logger = logging.getLogger(__name__)


class ResultSender(Protocol):
    """Sends an ended run's result on (``deliveries.sender.ResultDeliveries``); it
    never raises, so a delivery cannot change how the run ended."""

    async def send(self, database: Database, run_id: int) -> None: ...


class RunNotifier(Protocol):
    """Tells a run's owner that it ended (``notifications.Notifier``); never raises."""

    def run_ended(self, database: Database, run_id: int) -> bool: ...


@dataclass(frozen=True)
class RunPolicy:
    """The server's rules for runs (§7 Value Object); None is no bound."""

    limits: RunLimits = NO_LIMITS
    #: Runs one account may have queued, running or waiting (RUN_MAX_ACTIVE_PER_USER).
    max_active_per_user: int | None = None
    #: How long ``RunService.run_to_end`` waits for the end (RUN_WAIT_MAX_SECONDS).
    wait_seconds: float | None = None
    #: Free disk space a run must leave to start or resume (WORKSPACE_MIN_FREE_BYTES).
    disk: DiskReserve | None = None
    #: Where a finished or failed run's result is posted (DELIVERY_*); None sends nothing.
    deliveries: ResultSender | None = None
    #: Who emails the owner that a run ended (SMTP_*); None tells nobody.
    notifications: RunNotifier | None = None


def run_policy(settings: Settings) -> RunPolicy:
    return RunPolicy(
        run_limits(settings),
        settings.run_max_active_per_user,
        settings.run_wait_max_seconds,
        disk_reserve(settings),
        ResultDeliveries(secret_box_for(settings), send_policy(settings)),
        notifier(settings),
    )


#: The ceilings that bound what accounts spend of the server's key, by variable.
_CEILINGS: dict[str, Callable[[Settings], float | None]] = {
    "RUN_MAX_COST_USD": lambda settings: settings.run_max_cost_usd,
    "RUN_MAX_TOKENS": lambda settings: settings.run_max_tokens,
    "CHAT_MAX_TOKENS": lambda settings: settings.chat_max_tokens,
}


def unset_ceilings(settings: Settings) -> list[str]:
    """The ceilings left unset while accounts may spend the server's key; [] otherwise."""
    if not settings.allow_server_llm_key:
        return []
    return [name for name, value in _CEILINGS.items() if value(settings) is None]


def warn_about_unbounded_spending(settings: Settings) -> None:
    """At startup: say so when accounts spend the server's key with no ceiling.
    A cost ceiling alone does not bound a model with no known price."""
    if unset := unset_ceilings(settings):
        logger.warning(
            "runs.spending_unbounded allow_server_llm_key=true unset=%s: accounts "
            "without a key of their own spend the server's key without that ceiling",
            ",".join(unset),
        )
