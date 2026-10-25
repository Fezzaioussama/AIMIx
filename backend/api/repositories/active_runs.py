"""Data access for the runs that are active: queued, running or waiting
(AGENTS.md §7 Repository). How many one account has (the count a ``Quota`` on
starting and resuming runs checks), whether a schedule's previous run is still
going, and the startup recovery of the runs a stopped process left active.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, inspect, select, update
from sqlalchemy.orm import Session

from api.models import ACTIVE_RUN_STATUSES, Run, RunStatus, RunStep, StepStatus
from api.repositories.approvals import expire_pending
from api.repositories.bulk import changed as _changed


def count_of(user_id: int) -> Select[Any]:
    """How many of the account's runs are active."""
    return (
        select(func.count())
        .select_from(Run)
        .where(Run.user_id == user_id, Run.status.in_(ACTIVE_RUN_STATUSES))
    )


def of_schedule(session: Session, schedule_id: int) -> int | None:
    """The id of a run of this schedule that is still active; None when none is."""
    query = select(Run.id).where(
        Run.schedule_id == schedule_id, Run.status.in_(ACTIVE_RUN_STATUSES)
    )
    return session.scalar(query.order_by(Run.id.desc()).limit(1))


def interrupt_active(session: Session, now: datetime) -> int:
    """Mark the runs a previous process left queued, running or waiting as
    interrupted, their running steps as cancelled and their pending approvals
    as expired. A database without the runs table (not migrated yet) has none.

    Every active run in the database is taken for one the previous process left:
    the app runs as one process (docs/known-issues.md), and a second one sharing
    the database would have its own runs marked interrupted here."""
    if not inspect(session.connection()).has_table(Run.__tablename__):
        return 0
    stale = select(Run.id).where(Run.status.in_(ACTIVE_RUN_STATUSES))
    _changed(
        session,
        update(RunStep)
        .where(RunStep.run_id.in_(stale), RunStep.status == StepStatus.RUNNING)
        .values(status=StepStatus.CANCELLED, finished_at=now),
    )
    expire_pending(session, stale, now)
    interrupted = _changed(
        session,
        update(Run)
        .where(Run.status.in_(ACTIVE_RUN_STATUSES))
        .values(status=RunStatus.INTERRUPTED, finished_at=now),
    )
    session.commit()
    return interrupted
