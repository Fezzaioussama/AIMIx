"""Starts scheduled runs from inside the API process, off any request (AGENTS.md §6).

Every SCHEDULER_TICK_SECONDS, ``SchedulerLoop``'s thread asks the
``Scheduler`` to start what is due. Each due occurrence is first claimed with
a compare-and-set on ``next_run_at`` (``repositories/schedules.claim``) that
moves the schedule to its first time after now: of two processes, only the one
whose claim applied starts the run, and a schedule overdue after downtime runs
once, not once per missed time. A claimed occurrence starts like a manual run
(``RunService.start``), with the owner's LLM profile and a
``PipelineAgentGenerator``. When it cannot start (no API key, inputs the
pipeline no longer takes), the reason is saved on the schedule and logged, and
the schedule waits for its next time. An occurrence is started at most once: a
process that dies between a claim and its run loses that occurrence.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from api.db import Database
from api.exceptions import DomainError, NotFound
from api.models import Run, Schedule, User
from api.repositories import pipelines as pipeline_repository
from api.repositories import schedules as repository
from api.repositories import users
from api.security import SecretBox
from api.services import llm_settings
from api.services.llm import provider_config
from api.services.multiagent.contracts import StepAgent
from api.services.multiagent.step_agent import PipelineAgentGenerator
from api.services.run_executor import RunExecutor
from api.services.run_recorder import SERVER_ERROR_DETAIL, utcnow
from api.services.runs import RunService
from api.services.schedules.service import run_start, timing_of
from api.services.schedules.timing import next_run_after
from config.settings import Settings

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]


class OwnerAgents(Protocol):
    """Builds the step agent a schedule's run uses, for the schedule's owner."""

    def __call__(self, session: Session, owner: User) -> StepAgent: ...


@dataclass(frozen=True)
class ProfileAgents:
    """A schedule owner's step agent, built as a request of theirs builds one
    (``api/deps.pipeline_agent_factory``): their LLM profile, from the Settings
    page or else the environment, and a ``PipelineAgentGenerator``."""

    database: Database
    box: SecretBox

    def __call__(self, session: Session, owner: User) -> StepAgent:
        profile = llm_settings.resolve_profile(session, owner, self.box)
        # Fail fast (§6): with no key at all the run could only fail, so the
        # occurrence is reported on the schedule instead of as a failed run.
        provider_config(profile)
        return PipelineAgentGenerator(self.database, owner, profile)


class Scheduler:
    """Starts the run of every schedule that is due, once per occurrence."""

    def __init__(
        self, database: Database, runs: RunService, agents: OwnerAgents, clock: Clock = utcnow
    ) -> None:
        self._database = database
        self._runs = runs
        self._agents = agents
        self._clock = clock

    def tick(self) -> int:
        """Start what is due now; how many runs started."""
        now = self._clock()
        with self._database.session() as session:
            due = repository.due(session, now)
        return sum(self.fire(schedule, now) for schedule in due)

    def fire(self, schedule: Schedule, now: datetime) -> bool:
        """Start the run of one due occurrence, as seen at ``now``: True when
        this call did. When it cannot start, why is saved on the schedule."""
        try:
            return self._claim_and_start(schedule, now)
        except DomainError as error:
            logger.warning(
                "schedule.start_failed schedule_id=%s pipeline_id=%s code=%s",
                schedule.id,
                schedule.pipeline_id,
                error.code,
            )
            self._record(schedule.id, error.detail)
        except Exception:
            # The scheduler's boundary, like RunService._execute for a run: one
            # broken schedule must stop neither the others nor the loop.
            logger.exception("schedule.fire_crashed schedule_id=%s", schedule.id)
            self._record(schedule.id, SERVER_ERROR_DETAIL)
        return False

    def _claim_and_start(self, schedule: Schedule, now: datetime) -> bool:
        """Claim this occurrence, then start its run; False when another
        process (or an edit by its owner) took it first."""
        seen = schedule.next_run_at
        if seen is None:
            return False
        following = next_run_after(timing_of(schedule), now)
        with self._database.session() as session:
            if not repository.claim(session, schedule.id, seen, following):
                return False
        run = self._start(schedule.id)
        self._record(schedule.id, "")
        logger.info(
            "schedule.fired schedule_id=%s run_id=%s slot=%s", schedule.id, run.id, seen.isoformat()
        )
        return True

    def _start(self, schedule_id: int) -> Run:
        """Start the run of a claimed schedule, with what is saved now: an edit
        to its inputs since the tick began applies."""
        with self._database.session() as session:
            schedule = repository.get(session, schedule_id)
            if schedule is None:
                raise NotFound(f"Schedule {schedule_id} no longer exists.")
            owner = users.get(session, schedule.user_id)
            if owner is None:
                raise NotFound(f"The owner of schedule {schedule_id} no longer exists.")
            pipeline = pipeline_repository.get_owned(session, owner, schedule.pipeline_id)
            agent = self._agents(session, owner)
            start = run_start(schedule)
        return self._runs.start(owner, pipeline, start, agent).run

    def _record(self, schedule_id: int, error: str) -> None:
        with self._database.session() as session:
            repository.set_last_error(session, schedule_id, error)


class Background(Protocol):
    """Something the app starts with its lifespan and stops at shutdown."""

    def start(self) -> None: ...

    def stop(self) -> None: ...


class SchedulerLoop:
    """Calls ``tick`` (``Scheduler.tick``) every ``interval`` seconds on a
    daemon thread, from the app's startup to its shutdown (the FastAPI lifespan)."""

    def __init__(self, tick: Callable[[], object], interval: float, grace: float) -> None:
        self._tick = tick
        self._interval = interval
        self._grace = grace
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start ticking; the first tick comes one interval later. Every start
        has a stop signal of its own, so a thread that outlived a ``stop`` (a
        slow tick) is never brought back by the next ``start``."""
        if self._thread is not None:
            return
        self._stopping = threading.Event()
        self._thread = threading.Thread(
            target=self._serve, args=(self._stopping,), name="aimix-scheduler", daemon=True
        )
        self._thread.start()
        logger.info("scheduler.started tick_s=%.1f", self._interval)

    def stop(self) -> None:
        """Stop ticking; a tick in progress gets ``grace`` seconds to finish."""
        thread, self._thread = self._thread, None
        if thread is None:
            return
        self._stopping.set()
        thread.join(self._grace)
        logger.info("scheduler.stopped")

    def _serve(self, stopping: threading.Event) -> None:
        while not stopping.wait(self._interval):
            try:
                self._tick()
            except Exception:
                # The loop's boundary: a failed tick (the database briefly
                # unavailable, say) is logged, and the next one tries again.
                logger.exception("scheduler.tick_failed")


class IdleScheduler:
    """Stands in when SCHEDULER_ENABLED is false (Null Object): schedules stay
    saved, and none starts."""

    def start(self) -> None:
        logger.info("scheduler.disabled")

    def stop(self) -> None:
        return None


def build_scheduler(database: Database, executor: RunExecutor, settings: Settings) -> Background:
    """The app's scheduler (``create_app``): it starts runs on the app's executor."""
    if not settings.scheduler_enabled:
        return IdleScheduler()
    runs = RunService(database, executor, settings.pipeline_max_parallel_steps)
    scheduler = Scheduler(database, runs, ProfileAgents(database, SecretBox(settings.secret_key)))
    return SchedulerLoop(
        scheduler.tick, settings.scheduler_tick_seconds, settings.run_shutdown_grace_seconds
    )
