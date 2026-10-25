"""Data access for scheduled runs (AGENTS.md §7 Repository).

Lookups are by owner, so another account's schedule looks exactly like one
that does not exist (404). ``claim`` is the compare-and-set that lets exactly
one process start each occurrence. Each write commits its own transaction.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, Select, func, select, update
from sqlalchemy.orm import Session, load_only, selectinload

from api.exceptions import NotFound
from api.models import Run, Schedule, ScheduleFrequency, User


@dataclass(frozen=True)
class ScheduleFields:
    """Everything a write sets: the timing, the run inputs, whether it is on,
    and its next run (None while it is off)."""

    frequency: ScheduleFrequency
    hour: int
    minute: int
    weekday: int | None
    day_of_month: int | None
    timezone: str
    input_text: str
    input_values: dict[str, str]
    enabled: bool
    next_run_at: datetime | None


def _owned_by(user: User) -> Select[tuple[Schedule]]:
    return (
        select(Schedule).where(Schedule.user_id == user.id).options(selectinload(Schedule.pipeline))
    )


def for_user(session: Session, user: User, pipeline_id: int | None = None) -> list[Schedule]:
    """The user's schedules, oldest first, so the list keeps its order as it grows."""
    query = _owned_by(user)
    if pipeline_id is not None:
        query = query.where(Schedule.pipeline_id == pipeline_id)
    return list(session.scalars(query.order_by(Schedule.id)))


def get_owned(session: Session, user: User, schedule_id: int) -> Schedule:
    schedule = session.scalar(_owned_by(user).where(Schedule.id == schedule_id))
    if schedule is None:
        raise NotFound(f"Schedule {schedule_id} was not found.")
    return schedule


def count(session: Session, user: User) -> int:
    query = select(func.count()).select_from(Schedule).where(Schedule.user_id == user.id)
    return session.scalar(query) or 0


def _apply(schedule: Schedule, fields: ScheduleFields) -> None:
    for name, value in vars(fields).items():
        setattr(schedule, name, value)


def create(session: Session, user: User, pipeline_id: int, fields: ScheduleFields) -> Schedule:
    schedule = Schedule(user_id=user.id, pipeline_id=pipeline_id, last_error="")
    _apply(schedule, fields)
    session.add(schedule)
    session.commit()
    return get_owned(session, user, schedule.id)


def save(session: Session, schedule: Schedule, fields: ScheduleFields) -> Schedule:
    _apply(schedule, fields)
    session.commit()
    return schedule


def delete(session: Session, schedule: Schedule) -> None:
    session.delete(schedule)
    session.commit()


def due(session: Session, now: datetime) -> list[Schedule]:
    """Every schedule that is on and whose next run is not after ``now``, the
    longest-waiting first."""
    query = (
        select(Schedule)
        .where(Schedule.enabled.is_(True), Schedule.next_run_at <= now)
        .order_by(Schedule.next_run_at, Schedule.id)
    )
    return list(session.scalars(query))


def _changed(session: Session, statement: Any) -> int:
    """Execute a bulk UPDATE; how many rows it changed."""
    result = session.execute(statement, execution_options={"synchronize_session": False})
    return cast(CursorResult[Any], result).rowcount


def claim(session: Session, schedule_id: int, seen: datetime, following: datetime) -> bool:
    """Compare-and-set: move the schedule from the occurrence ``seen`` to
    ``following``, only while it is on and still due at ``seen``. True for the
    one caller that moved it, which then starts that occurrence."""
    claimed = _changed(
        session,
        update(Schedule)
        .where(
            Schedule.id == schedule_id,
            Schedule.enabled.is_(True),
            Schedule.next_run_at == seen,
        )
        .values(next_run_at=following),
    )
    session.commit()
    return claimed == 1


def set_last_error(session: Session, schedule_id: int, error: str) -> None:
    """Why the latest occurrence could not start; "" once one has."""
    _changed(session, update(Schedule).where(Schedule.id == schedule_id).values(last_error=error))
    session.commit()


#: What a schedule shows of its latest run.
LAST_RUN_COLUMNS = (Run.id, Run.schedule_id, Run.status, Run.created_at)


def last_runs(session: Session, schedule_ids: Collection[int]) -> dict[int, Run]:
    """The newest run each of these schedules started (run ids grow with time),
    by schedule id; a schedule whose runs were all deleted has none."""
    if not schedule_ids:
        return {}
    newest = (
        select(func.max(Run.id))
        .where(Run.schedule_id.in_(schedule_ids))
        .group_by(Run.schedule_id)
    )
    rows = session.scalars(
        select(Run).where(Run.id.in_(newest)).options(load_only(*LAST_RUN_COLUMNS))
    )
    return {run.schedule_id: run for run in rows if run.schedule_id is not None}
