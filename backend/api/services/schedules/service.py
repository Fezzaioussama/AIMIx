"""The Schedules use cases: a user's pipelines, run on their own.

Takes and returns plain Python values (AGENTS.md §2). A schedule's timing goes
through ``timing.checked`` and its run inputs through the rules every run
applies (``pipelines.prepare_run``) before anything is saved, so a schedule
that saves is one whose runs can start.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, time

from sqlalchemy.orm import Session

from api.exceptions import ValidationFailed
from api.models import Run, RunStatus, RunTrigger, Schedule, ScheduleFrequency, User
from api.repositories import pipelines as pipeline_repository
from api.repositories import schedules as repository
from api.repositories.schedules import ScheduleFields
from api.services.multiagent.contracts import StepAgent
from api.services.pipelines import prepare_run
from api.services.runs import RunService, RunStart
from api.services.schedules.timing import Timing, checked, next_run_after

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScheduleAccess:
    """The signed-in user's schedules, for one request (built in api/deps.py)."""

    session: Session
    user: User
    #: SCHEDULES_MAX_PER_USER.
    max_per_user: int
    now: datetime


@dataclass(frozen=True)
class ScheduleDraft:
    """A new schedule of one of the user's pipelines."""

    pipeline_id: int
    timing: Timing
    start: RunStart = field(default_factory=RunStart)
    enabled: bool = True


@dataclass(frozen=True)
class TimingEdit:
    """Timing fields to change; None keeps the saved one."""

    frequency: ScheduleFrequency | None = None
    at: time | None = None
    weekday: int | None = None
    day_of_month: int | None = None
    timezone: str | None = None

    def applied_to(self, timing: Timing) -> Timing:
        return Timing(
            frequency=timing.frequency if self.frequency is None else self.frequency,
            timezone=timing.timezone if self.timezone is None else self.timezone,
            at=timing.at if self.at is None else self.at,
            weekday=timing.weekday if self.weekday is None else self.weekday,
            day_of_month=timing.day_of_month if self.day_of_month is None else self.day_of_month,
        )


@dataclass(frozen=True)
class ScheduleEdit:
    """Changes to a schedule: its timing field by field, its run inputs as a
    whole (``start``), and whether it is on. None keeps what is saved."""

    timing: TimingEdit = field(default_factory=TimingEdit)
    start: RunStart | None = None
    enabled: bool | None = None


@dataclass(frozen=True)
class LastRunView:
    id: int
    status: RunStatus
    created_at: datetime


@dataclass(frozen=True)
class ScheduleView:
    """A schedule as the API shows it, with its pipeline's name and inputs."""

    id: int
    pipeline_id: int
    pipeline_name: str
    pipeline_inputs: list[dict[str, str]]
    frequency: ScheduleFrequency
    at: time
    weekday: int | None
    day_of_month: int | None
    timezone: str
    input_text: str
    input_values: dict[str, str]
    enabled: bool
    next_run_at: datetime | None
    last_run: LastRunView | None
    last_error: str
    created_at: datetime


def timing_of(schedule: Schedule) -> Timing:
    return Timing(
        frequency=schedule.frequency,
        timezone=schedule.timezone,
        at=time(schedule.hour, schedule.minute),
        weekday=schedule.weekday,
        day_of_month=schedule.day_of_month,
    )


def run_start(schedule: Schedule) -> RunStart:
    """What each of the schedule's runs is started with, marked as its own."""
    return RunStart(
        schedule.input_text, dict(schedule.input_values), RunTrigger.SCHEDULE, schedule.id
    )


def _fields(
    timing: Timing, start: RunStart, enabled: bool, next_run_at: datetime | None
) -> ScheduleFields:
    return ScheduleFields(
        frequency=timing.frequency,
        hour=timing.at.hour,
        minute=timing.at.minute,
        weekday=timing.weekday,
        day_of_month=timing.day_of_month,
        timezone=timing.timezone,
        input_text=start.text,
        input_values=dict(start.values),
        enabled=enabled,
        next_run_at=next_run_at,
    )


def _next_run(row: Schedule, timing: Timing, enabled: bool, now: datetime) -> datetime | None:
    """None while off. While its timing stays the same, the saved one, so an
    occurrence that is due still starts; else the first time after ``now``."""
    if not enabled:
        return None
    if row.enabled and row.next_run_at is not None and timing == timing_of(row):
        return row.next_run_at
    return next_run_after(timing, now)


def _error_after(row: Schedule, edit: ScheduleEdit, timing: Timing, enabled: bool) -> str:
    """What ``last_error`` says once this edit is saved. An edit that changes what the
    schedule runs or when (or turns it on) starts a new configuration, which has not
    failed yet, so the old reason goes; any other edit keeps it."""
    reconfigured = (
        edit.start is not None or timing != timing_of(row) or (enabled and not row.enabled)
    )
    return "" if reconfigured else row.last_error


def _last_run(run: Run | None) -> LastRunView | None:
    return None if run is None else LastRunView(run.id, run.status, run.created_at)


def _view(row: Schedule, last_run: Run | None) -> ScheduleView:
    return ScheduleView(
        id=row.id,
        pipeline_id=row.pipeline_id,
        pipeline_name=row.pipeline.name,
        pipeline_inputs=list(row.pipeline.inputs or []),
        frequency=row.frequency,
        at=time(row.hour, row.minute),
        weekday=row.weekday,
        day_of_month=row.day_of_month,
        timezone=row.timezone,
        input_text=row.input_text,
        input_values=dict(row.input_values),
        enabled=row.enabled,
        next_run_at=row.next_run_at,
        last_run=_last_run(last_run),
        last_error=row.last_error,
        created_at=row.created_at,
    )


def _one_view(session: Session, row: Schedule) -> ScheduleView:
    return _view(row, repository.last_runs(session, [row.id]).get(row.id))


def list_views(access: ScheduleAccess, pipeline_id: int | None = None) -> list[ScheduleView]:
    rows = repository.for_user(access.session, access.user, pipeline_id)
    last = repository.last_runs(access.session, [row.id for row in rows])
    return [_view(row, last.get(row.id)) for row in rows]


def _check_inputs(access: ScheduleAccess, pipeline_id: int, start: RunStart) -> None:
    """The pipeline is the user's, and takes these inputs as a run would."""
    pipeline = pipeline_repository.get_owned(access.session, access.user, pipeline_id)
    prepare_run(pipeline, start.text, start.values)


def create(access: ScheduleAccess, draft: ScheduleDraft) -> ScheduleView:
    limit = access.max_per_user
    if repository.count(access.session, access.user) >= limit:
        raise ValidationFailed(f"You can have up to {limit} schedules. Delete one first.")
    _check_inputs(access, draft.pipeline_id, draft.start)
    timing = checked(draft.timing)
    next_run = next_run_after(timing, access.now) if draft.enabled else None
    fields = _fields(timing, draft.start, draft.enabled, next_run)
    row = repository.create(access.session, access.user, draft.pipeline_id, fields)
    logger.info(
        "schedule.created user_id=%s schedule_id=%s pipeline_id=%s frequency=%s",
        access.user.id,
        row.id,
        row.pipeline_id,
        timing.frequency.value,
    )
    return _one_view(access.session, row)


def update(access: ScheduleAccess, schedule_id: int, edit: ScheduleEdit) -> ScheduleView:
    """Apply an edit; sending the same edit twice leaves the same state.

    The inputs are checked again when they change or the schedule is turned
    on; turning it off always works. Its next run is worked out again when
    its timing changes or it is turned on, and the reason its last time could
    not start goes when the edit gives it something new to try."""
    row = repository.get_owned(access.session, access.user, schedule_id)
    timing = checked(edit.timing.applied_to(timing_of(row)))
    start = edit.start or RunStart(row.input_text, row.input_values)
    enabled = row.enabled if edit.enabled is None else edit.enabled
    if enabled and (edit.start is not None or not row.enabled):
        _check_inputs(access, row.pipeline_id, start)
    fields = _fields(timing, start, enabled, _next_run(row, timing, enabled, access.now))
    repository.save(
        access.session, row, replace(fields, last_error=_error_after(row, edit, timing, enabled))
    )
    logger.info(
        "schedule.updated user_id=%s schedule_id=%s enabled=%s", access.user.id, row.id, enabled
    )
    return _one_view(access.session, row)


def delete(access: ScheduleAccess, schedule_id: int) -> None:
    """Its runs stay in the history, no longer linked to it."""
    row = repository.get_owned(access.session, access.user, schedule_id)
    repository.delete(access.session, row)
    logger.info("schedule.deleted user_id=%s schedule_id=%s", access.user.id, schedule_id)


def preview(timing: Timing, now: datetime) -> datetime:
    """When a schedule with ``timing`` would first run after ``now``; nothing is saved."""
    return next_run_after(checked(timing), now)


def run_now(access: ScheduleAccess, schedule_id: int, runs: RunService, agent: StepAgent) -> Run:
    """Start one of the schedule's runs at once, with its inputs, as a run of
    the schedule; its timing does not change."""
    row = repository.get_owned(access.session, access.user, schedule_id)
    pipeline = pipeline_repository.get_owned(access.session, access.user, row.pipeline_id)
    run = runs.start(access.user, pipeline, run_start(row), agent).run
    logger.info("schedule.run_now schedule_id=%s run_id=%s", row.id, run.id)
    return run
