"""Starts scheduled runs from inside the API process, off any request (AGENTS.md §6).

Every SCHEDULER_TICK_SECONDS, ``SchedulerLoop``'s thread asks the
``Scheduler`` to start what is due. Each due occurrence is first claimed with
a compare-and-set on ``next_run_at`` (``repositories/schedules.claim``) that
moves the schedule to its first time after now: of two processes, only the one
whose claim applied starts the run, and a schedule overdue after downtime runs
once, not once per missed time. A claimed occurrence starts like a manual run
(``RunService.start``), with the owner's LLM profile and a
``PipelineAgentGenerator`` (``owner_agents.ProfileAgents``). When it cannot
start (no API key, inputs the pipeline no longer takes), the reason is saved on
the schedule and logged, and the schedule waits for its next time. So does an
occurrence that comes while the schedule's previous run is still active: it is
skipped, not queued behind it, and the schedule says why. The claim stays on
the schedule (``claimed_occurrence``) until its run is saved, or it is passed
over or fails to start, so an occurrence a process died on is not lost: the
first tick after the restart starts it (``replay``), unless a run of the
schedule was saved since.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from api.db import Database
from api.exceptions import DomainError, NotFound
from api.models import Run, Schedule
from api.repositories import active_runs, users
from api.repositories import pipelines as pipeline_repository
from api.repositories import schedules as repository
from api.security import secret_box_for
from api.services.notifications import notifier
from api.services.owner_agents import OwnerAgents, ProfileAgents
from api.services.run_executor import RunExecutor
from api.services.run_policy import run_policy
from api.services.run_recorder import SERVER_ERROR_DETAIL, utcnow
from api.services.runs import RunService
from api.services.schedules.service import run_start, timing_of
from api.services.schedules.timing import next_run_after
from config.settings import Settings

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]


class ScheduleNotifier(Protocol):
    """Tells a schedule's owner why its run could not start (``notifications.Notifier``)."""

    def schedule_failed(self, database: Database, schedule_id: int, error: str) -> bool: ...


@dataclass(frozen=True)
class SchedulerHooks:
    """What the scheduler calls besides the database: the clock, and who is told
    that a schedule's run could not start (None tells nobody)."""

    clock: Clock = utcnow
    notifier: ScheduleNotifier | None = None


class Scheduler:
    """Starts the run of every schedule that is due, once per occurrence."""

    def __init__(
        self,
        database: Database,
        runs: RunService,
        agents: OwnerAgents,
        hooks: SchedulerHooks = SchedulerHooks(),
    ) -> None:
        self._database = database
        self._runs = runs
        self._agents = agents
        self._clock = hooks.clock
        self._notifier = hooks.notifier
        self._replayed = False

    def tick(self) -> int:
        """Start what is due now; how many runs started. The first tick also
        starts the occurrences a stopped process claimed and never started."""
        now = self._clock()
        with self._database.session() as session:
            claimed: list[Schedule] = [] if self._replayed else repository.claimed(session)
            due = repository.due(session, now)
        replayed = sum(self.replay(schedule) for schedule in claimed)
        self._replayed = True
        return replayed + sum(self.fire(schedule, now) for schedule in due)

    def fire(self, schedule: Schedule, now: datetime) -> bool:
        """Start the run of one due occurrence, as seen at ``now``: True when
        this call did. When it cannot start, why is saved on the schedule."""
        return self._guarded(schedule, lambda: self._claim_and_start(schedule, now))

    def replay(self, schedule: Schedule) -> bool:
        """Start the occurrence a stopped process claimed but never started: True
        when this call did. A run of the schedule saved since (the process died
        just after saving it), or a schedule switched off since, only settles
        the claim."""
        slot = schedule.claimed_occurrence
        if slot is None:
            return False
        with self._database.session() as session:
            saved = repository.run_since(session, schedule.id, slot)
        if saved or not schedule.enabled:
            self._record(schedule.id, "")
            return False
        logger.warning("schedule.replayed schedule_id=%s slot=%s", schedule.id, slot.isoformat())
        return self._guarded(schedule, lambda: self._start_claimed(schedule, slot))

    def _guarded(self, schedule: Schedule, start: Callable[[], bool]) -> bool:
        """Run ``start``; when it cannot start the run, why is saved on the schedule."""
        try:
            return start()
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
        return self._start_claimed(schedule, seen)

    def _start_claimed(self, schedule: Schedule, slot: datetime) -> bool:
        """Start the run of the occurrence ``slot``, whose claim this process holds,
        unless the schedule's previous run is still active: then it is passed over."""
        with self._database.session() as session:
            previous = active_runs.of_schedule(session, schedule.id)
        if previous is not None:
            return self._skip(schedule, slot, previous)
        run = self._start(schedule.id)
        self._record(schedule.id, "")
        logger.info(
            "schedule.fired schedule_id=%s run_id=%s slot=%s", schedule.id, run.id, slot.isoformat()
        )
        return True

    def _skip(self, schedule: Schedule, slot: datetime, previous: int) -> bool:
        """Pass over a claimed occurrence: its previous run is still active."""
        logger.info(
            "schedule.skipped schedule_id=%s previous_run_id=%s slot=%s",
            schedule.id,
            previous,
            slot.isoformat(),
        )
        self._record(
            schedule.id,
            f"Skipped a run: run {previous} of this schedule was still in progress.",
        )
        return False

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
        """Settle the occurrence: its claim is released, ``error`` says why it could
        not start ("" when it did), and a reason the schedule did not already
        show is told to its owner."""
        with self._database.session() as session:
            schedule = repository.get(session, schedule_id)
            news = error != "" and schedule is not None and schedule.last_error != error
            repository.set_last_error(session, schedule_id, error)
        if news and self._notifier is not None:
            self._notifier.schedule_failed(self._database, schedule_id, error)


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
    runs = RunService(
        database, executor, settings.pipeline_max_parallel_steps, run_policy(settings)
    )
    hooks = SchedulerHooks(notifier=notifier(settings))
    scheduler = Scheduler(database, runs, ProfileAgents(database, secret_box_for(settings)), hooks)
    return SchedulerLoop(
        scheduler.tick, settings.scheduler_tick_seconds, settings.run_shutdown_grace_seconds
    )
