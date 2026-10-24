"""Data access for pipeline runs (AGENTS.md §7 Repository).

Ownership filtering lives here, so someone else's run is indistinguishable
from a missing one (404). Status changes are compare-and-set: each applies only
while the run (or step) is in a status the caller expects, so a request thread
stopping or resuming a run and the executor recording it never overwrite each
other. Each write commits its own transaction.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, Select, func, inspect, select, update
from sqlalchemy.orm import Session, load_only, selectinload

from api.exceptions import NotFound
from api.models import ACTIVE_RUN_STATUSES, Run, RunStatus, RunStep, StepStatus, User

#: What a run summary needs; the long texts (definition, inputs, outputs) stay unloaded.
SUMMARY_COLUMNS = (
    Run.id,
    Run.pipeline_id,
    Run.pipeline_name,
    Run.status,
    Run.error_code,
    Run.error_detail,
    Run.created_at,
    Run.started_at,
    Run.finished_at,
)


def _unstarted_step() -> dict[str, Any]:
    """How a step looks before it runs, and again when a resumed run will redo it."""
    return {
        "status": StepStatus.PENDING,
        "input_used": "",
        "output": "",
        "tool_calls": [],
        "error_code": "",
        "error_detail": "",
        "started_at": None,
        "finished_at": None,
    }


@dataclass(frozen=True)
class NewRun:
    """A run to save, queued; ``steps`` holds each step's column values."""

    pipeline_id: int | None
    pipeline_name: str
    definition: dict[str, Any]
    input_text: str
    input_values: dict[str, str]
    steps: list[dict[str, Any]]


@dataclass(frozen=True)
class RunQuery:
    """One page of a user's runs, newest first, optionally of one pipeline."""

    limit: int
    offset: int = 0
    pipeline_id: int | None = None


@dataclass(frozen=True)
class RunPage:
    items: list[Run]
    total: int


@dataclass(frozen=True)
class RunEnding:
    """How a run ends: its final status, from which statuses it may get there,
    and what its steps still running become."""

    status: RunStatus
    expected: frozenset[RunStatus]
    leftover_steps: StepStatus
    values: Mapping[str, Any] = field(default_factory=dict)


def _with_steps() -> Select[tuple[Run]]:
    return select(Run).options(selectinload(Run.steps))


def create(session: Session, user: User, new: NewRun) -> Run:
    run = Run(
        user_id=user.id,
        pipeline_id=new.pipeline_id,
        pipeline_name=new.pipeline_name,
        definition=new.definition,
        input_text=new.input_text,
        input_values=new.input_values,
        status=RunStatus.QUEUED,
        steps=[RunStep(**_unstarted_step(), **step) for step in new.steps],
    )
    session.add(run)
    session.commit()
    return run


def get_owned(session: Session, user: User, run_id: int) -> Run:
    """A run of ``user``'s with its steps, or NotFound."""
    run = session.scalar(_with_steps().where(Run.id == run_id, Run.user_id == user.id))
    if run is None:
        raise NotFound(f"Run {run_id} was not found.")
    return run


def load(session: Session, run_id: int) -> Run | None:
    """A run with its steps, whoever owns it — for code that already checked."""
    return session.scalar(_with_steps().where(Run.id == run_id))


def page_for_user(session: Session, user: User, query: RunQuery) -> RunPage:
    """Summaries of ``user``'s runs, newest first, and how many there are in all."""
    filters = [Run.user_id == user.id]
    if query.pipeline_id is not None:
        filters.append(Run.pipeline_id == query.pipeline_id)
    total = session.scalar(select(func.count()).select_from(Run).where(*filters)) or 0
    rows = session.scalars(
        select(Run)
        .where(*filters)
        .options(load_only(*SUMMARY_COLUMNS))
        .order_by(Run.created_at.desc(), Run.id.desc())
        .limit(query.limit)
        .offset(query.offset)
    )
    return RunPage(list(rows), total)


def _changed(session: Session, statement: Any) -> int:
    """Execute a bulk UPDATE; how many rows it changed."""
    result = session.execute(statement, execution_options={"synchronize_session": False})
    return cast(CursorResult[Any], result).rowcount


def set_status(
    session: Session, run_id: int, expected: Collection[RunStatus], values: Mapping[str, Any]
) -> bool:
    """Compare-and-set: apply ``values`` (which include the new status) only
    while the run is in one of ``expected``. False when it was not."""
    changed = _changed(
        session, update(Run).where(Run.id == run_id, Run.status.in_(expected)).values(**values)
    )
    session.commit()
    return changed == 1


def set_step(
    session: Session,
    run_id: int,
    step_order: int,
    expected: Collection[StepStatus],
    values: Mapping[str, Any],
) -> bool:
    """Compare-and-set on one step, like ``set_status``."""
    changed = _changed(
        session,
        update(RunStep)
        .where(
            RunStep.run_id == run_id,
            RunStep.step_order == step_order,
            RunStep.status.in_(expected),
        )
        .values(**values),
    )
    session.commit()
    return changed == 1


def end(session: Session, run_id: int, ending: RunEnding, now: datetime) -> bool:
    """Give the run its final status (compare-and-set) and settle the steps it
    left running, in one transaction. False when the run had already ended."""
    ended = _changed(
        session,
        update(Run)
        .where(Run.id == run_id, Run.status.in_(ending.expected))
        .values(status=ending.status, finished_at=now, **ending.values),
    )
    if ended:
        _changed(
            session,
            update(RunStep)
            .where(RunStep.run_id == run_id, RunStep.status == StepStatus.RUNNING)
            .values(status=ending.leftover_steps, finished_at=now),
        )
    session.commit()
    return ended == 1


def reopen(session: Session, run_id: int, resumable: Collection[RunStatus]) -> bool:
    """Queue a stopped run again (compare-and-set from ``resumable``) and reset
    every step that did not succeed, in one transaction."""
    reopened = _changed(
        session,
        update(Run)
        .where(Run.id == run_id, Run.status.in_(resumable))
        .values(
            status=RunStatus.QUEUED,
            final_output="",
            error_code="",
            error_detail="",
            finished_at=None,
        ),
    )
    if reopened:
        _changed(
            session,
            update(RunStep)
            .where(RunStep.run_id == run_id, RunStep.status != StepStatus.SUCCEEDED)
            .values(**_unstarted_step()),
        )
    session.commit()
    return reopened == 1


def delete(session: Session, run: Run) -> None:
    session.delete(run)
    session.commit()


def interrupt_active(session: Session, now: datetime) -> int:
    """Mark the runs a previous process left queued or running as interrupted,
    and their running steps as cancelled. A database without the runs table
    (not migrated yet) has none."""
    if not inspect(session.connection()).has_table(Run.__tablename__):
        return 0
    stale = select(Run.id).where(Run.status.in_(ACTIVE_RUN_STATUSES))
    _changed(
        session,
        update(RunStep)
        .where(RunStep.run_id.in_(stale), RunStep.status == StepStatus.RUNNING)
        .values(status=StepStatus.CANCELLED, finished_at=now),
    )
    interrupted = _changed(
        session,
        update(Run)
        .where(Run.status.in_(ACTIVE_RUN_STATUSES))
        .values(status=RunStatus.INTERRUPTED, finished_at=now),
    )
    session.commit()
    return interrupted
