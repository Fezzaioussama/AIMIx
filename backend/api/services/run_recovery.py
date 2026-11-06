"""At startup, the runs a stopped process left behind go on by themselves.

A process that stops (a deploy, a crash) leaves runs queued, running or waiting
that cannot finish there; ``interrupt_abandoned_runs`` marks them interrupted.
With RUN_AUTO_RESUME on, ``StartupRecovery`` then queues every interrupted run
that ended within RUN_AUTO_RESUME_MAX_AGE_SECONDS again, the way its owner
would from the Runs screen (``RunService.resume``, on the owner's own key and
profile), so the steps that succeeded are kept. A run that cannot be resumed
(its owner has no key, it is over its spending limit, the account has too many
active runs) stays interrupted with the reason in its error detail, to be tried
again at the next startup; an older one is left to its owner. Plain Python
values in and out (AGENTS.md §2).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from api.db import Database
from api.exceptions import DomainError, NotFound
from api.models import RunStatus
from api.repositories import active_runs, users
from api.repositories import runs as repository
from api.security import secret_box_for
from api.services.owner_agents import OwnerAgents, ProfileAgents
from api.services.run_executor import RunExecutor
from api.services.run_policy import run_policy
from api.services.run_recorder import SERVER_ERROR_CODE, SERVER_ERROR_DETAIL, utcnow
from api.services.runs import RunService, interrupt_abandoned_runs
from config.settings import Settings

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]

#: Starts the error detail of a run a startup could not resume.
NOT_RESUMED = "Not resumed after the restart: "


@dataclass(frozen=True)
class RecoveryPolicy:
    """RUN_AUTO_RESUME and RUN_AUTO_RESUME_MAX_AGE_SECONDS (§7 Value Object)."""

    auto_resume: bool
    max_age: timedelta


def recovery_policy(settings: Settings) -> RecoveryPolicy:
    return RecoveryPolicy(
        settings.run_auto_resume, timedelta(seconds=settings.run_auto_resume_max_age_seconds)
    )


@dataclass(frozen=True)
class Recovery:
    """What a startup found and did (§7 DTO): the runs it just interrupted, the
    runs queued again, and the runs left interrupted with the reason on them."""

    interrupted: int
    resumed: tuple[int, ...] = ()
    left: tuple[int, ...] = ()


class StartupRecovery:
    """Settles the runs of a previous process and resumes them, once, at startup."""

    def __init__(
        self,
        database: Database,
        runs: RunService,
        agents: OwnerAgents,
        policy: RecoveryPolicy,
        clock: Clock = utcnow,
    ) -> None:
        self._database = database
        self._runs = runs
        self._agents = agents
        self._policy = policy
        self._clock = clock

    def run(self) -> Recovery:
        interrupted = interrupt_abandoned_runs(self._database)
        if not self._policy.auto_resume:
            return Recovery(interrupted)
        since = self._clock() - self._policy.max_age
        with self._database.session() as session:
            found = active_runs.interrupted_since(session, since)
        resumed: list[int] = []
        left: list[int] = []
        for run_id, owner_id in found:
            (resumed if self._resume(run_id, owner_id) else left).append(run_id)
        if found:
            logger.info("run.recovered_on_startup resumed=%d left=%d", len(resumed), len(left))
        return Recovery(interrupted, tuple(resumed), tuple(left))

    def _resume(self, run_id: int, owner_id: int) -> bool:
        """Queue the run again as its owner would; False when it could not be,
        with the reason recorded on the run."""
        try:
            with self._database.session() as session:
                owner = users.get(session, owner_id)
                if owner is None:
                    raise NotFound(f"The owner of run {run_id} no longer exists.")
                agent = self._agents(session, owner)
            self._runs.resume(owner, run_id, agent)
        except DomainError as error:
            self._leave(run_id, error.code, error.detail)
            return False
        except Exception:
            # The recovery's boundary, like the scheduler's for one schedule: one
            # broken run must stop neither the others nor the app from starting.
            logger.exception("run.resume_crashed_on_startup run_id=%s", run_id)
            self._leave(run_id, SERVER_ERROR_CODE, SERVER_ERROR_DETAIL)
            return False
        logger.info("run.resumed_on_startup run_id=%s", run_id)
        return True

    def _leave(self, run_id: int, code: str, detail: str) -> None:
        values = {"error_code": code, "error_detail": NOT_RESUMED + detail}
        with self._database.session() as session:
            repository.set_status(session, run_id, [RunStatus.INTERRUPTED], values)
        logger.warning("run.not_resumed_on_startup run_id=%s code=%s", run_id, code)


def startup_recovery(
    database: Database, executor: RunExecutor, settings: Settings
) -> StartupRecovery:
    """The app's recovery (``create_app``): resumed runs execute on the app's executor."""
    runs = RunService(
        database, executor, settings.pipeline_max_parallel_steps, run_policy(settings)
    )
    agents = ProfileAgents(database, secret_box_for(settings))
    return StartupRecovery(database, runs, agents, recovery_policy(settings))
