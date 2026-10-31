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
from typing import Any

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session, load_only, selectinload

from api.exceptions import NotFound
from api.models import (
    COMPLETED_STEP_STATUSES,
    RESUMABLE_RUN_STATUSES,
    Run,
    RunStatus,
    RunStep,
    RunTrigger,
    StepStatus,
    User,
)
from api.repositories import active_runs, quota
from api.repositories.approvals import expire_pending
from api.repositories.bulk import changed as _changed
from llm.usage import TokenUsage

#: What a run summary needs; the long texts (definition, inputs, outputs) stay unloaded.
SUMMARY_COLUMNS = (
    Run.id,
    Run.pipeline_id,
    Run.pipeline_name,
    Run.trigger,
    Run.schedule_id,
    Run.status,
    Run.error_code,
    Run.error_detail,
    Run.created_at,
    Run.started_at,
    Run.finished_at,
    Run.max_cost_usd,
    Run.max_tokens,
)
#: What a summary reads of each step: its usage, which adds up to the run's.
STEP_USAGE_COLUMNS = (RunStep.input_tokens, RunStep.output_tokens, RunStep.cost_usd)


def unstarted_step() -> dict[str, Any]:
    """How a step looks before it runs, and again when a resumed run or a review
    loop will redo it. What it used (tokens and cost) and the round it is in are
    not part of it: they carry over."""
    return {
        "status": StepStatus.PENDING,
        "input_used": "",
        "output": "",
        "tool_calls": [],
        "error_code": "",
        "error_detail": "",
        "verdict": None,
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
    #: Spending limits; None is no limit.
    max_cost_usd: float | None = None
    max_tokens: int | None = None
    trigger: RunTrigger = RunTrigger.MANUAL
    schedule_id: int | None = None


@dataclass(frozen=True)
class RunQuery:
    """One page of a user's runs, newest first, optionally of one pipeline or status."""

    limit: int
    offset: int = 0
    pipeline_id: int | None = None
    status: RunStatus | None = None


@dataclass(frozen=True)
class RunPage:
    items: list[Run]
    total: int


@dataclass(frozen=True)
class StepChange:
    """A compare-and-set on one step: set ``values`` only while the step is in
    one of the ``expected`` statuses."""

    step_order: int
    expected: frozenset[StepStatus]
    values: Mapping[str, Any]


@dataclass(frozen=True)
class RunEnding:
    """How a run ends: its final status, from which statuses it may get there,
    and what its steps still running become."""

    status: RunStatus
    expected: frozenset[RunStatus]
    leftover_steps: StepStatus
    values: Mapping[str, Any] = field(default_factory=dict)


def _with_steps() -> Select[tuple[Run]]:
    return select(Run).options(selectinload(Run.steps), selectinload(Run.pending_approvals))


def create(session: Session, user: User, new: NewRun, cap: quota.Quota | None = None) -> Run:
    """Save a queued run; with ``cap``, only while the user stays within it."""
    if cap is not None:
        quota.lock_owner(session, user.id)
    run = Run(
        user_id=user.id,
        pipeline_id=new.pipeline_id,
        pipeline_name=new.pipeline_name,
        definition=new.definition,
        input_text=new.input_text,
        input_values=new.input_values,
        trigger=new.trigger,
        schedule_id=new.schedule_id,
        status=RunStatus.QUEUED,
        max_cost_usd=new.max_cost_usd,
        max_tokens=new.max_tokens,
        steps=[RunStep(**unstarted_step(), **step) for step in new.steps],
    )
    session.add(run)
    if cap is not None:
        quota.enforce(session, active_runs.count_of(user.id), cap)
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


def all_for_user(session: Session, user: User) -> list[Run]:
    """Every run of ``user``'s with its steps, newest first (their data export)."""
    query = _with_steps().where(Run.user_id == user.id)
    return list(session.scalars(query.order_by(Run.created_at.desc(), Run.id.desc())))


def page_for_user(session: Session, user: User, query: RunQuery) -> RunPage:
    """Summaries of ``user``'s runs, newest first, and how many there are in all."""
    filters = [Run.user_id == user.id]
    if query.pipeline_id is not None:
        filters.append(Run.pipeline_id == query.pipeline_id)
    if query.status is not None:
        filters.append(Run.status == query.status)
    total = session.scalar(select(func.count()).select_from(Run).where(*filters)) or 0
    rows = session.scalars(
        select(Run)
        .where(*filters)
        .options(load_only(*SUMMARY_COLUMNS))
        .options(selectinload(Run.steps).load_only(*STEP_USAGE_COLUMNS))
        .order_by(Run.created_at.desc(), Run.id.desc())
        .limit(query.limit)
        .offset(query.offset)
    )
    return RunPage(list(rows), total)


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


def set_step(session: Session, run_id: int, change: StepChange) -> bool:
    """Compare-and-set on one step, like ``set_status``."""
    changed = _changed(
        session,
        update(RunStep)
        .where(
            RunStep.run_id == run_id,
            RunStep.step_order == change.step_order,
            RunStep.status.in_(change.expected),
        )
        .values(**change.values),
    )
    session.commit()
    return changed == 1


def end(session: Session, run_id: int, ending: RunEnding, now: datetime) -> bool:
    """Give the run its final status (compare-and-set) and settle the steps it
    left running and the approvals it left pending, in one transaction. False
    when the run had already ended."""
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
        expire_pending(session, [run_id], now)
    session.commit()
    return ended == 1


def reopen(
    session: Session, run: Run, values: Mapping[str, Any], cap: quota.Quota | None = None
) -> bool:
    """Queue a stopped run again (compare-and-set from a resumable status), setting
    ``values`` too (its spending limits), and reset every step that neither
    succeeded nor was skipped, in one transaction; with ``cap``, only while its
    owner stays within it. A step keeps its usage (that was spent) and the
    review round it was in."""
    if cap is not None:
        quota.lock_owner(session, run.user_id)
    run_id = run.id
    reopened = _changed(
        session,
        update(Run)
        .where(Run.id == run_id, Run.status.in_(RESUMABLE_RUN_STATUSES))
        .values(
            status=RunStatus.QUEUED,
            final_output="",
            error_code="",
            error_detail="",
            finished_at=None,
            **values,
        ),
    )
    if reopened and cap is not None:
        quota.enforce(session, active_runs.count_of(run.user_id), cap)
    if reopened:
        _changed(
            session,
            update(RunStep)
            .where(RunStep.run_id == run_id, RunStep.status.notin_(COMPLETED_STEP_STATUSES))
            .values(**unstarted_step()),
        )
    session.commit()
    return reopened == 1


def add_step_usage(session: Session, run_id: int, step_order: int, usage: TokenUsage) -> None:
    """Add one model call's tokens and cost to its step. The database adds them
    (``SET x = x + n``), so parallel writers never lose or double an update; an
    unknown cost leaves the step's cost as it was."""
    values: dict[str, Any] = {
        "input_tokens": RunStep.input_tokens + usage.input_tokens,
        "output_tokens": RunStep.output_tokens + usage.output_tokens,
    }
    if usage.cost_usd is not None:
        values["cost_usd"] = func.coalesce(RunStep.cost_usd, 0.0) + usage.cost_usd
    _changed(
        session,
        update(RunStep)
        .where(RunStep.run_id == run_id, RunStep.step_order == step_order)
        .values(**values),
    )
    session.commit()


def delete(session: Session, run: Run) -> None:
    session.delete(run)
    session.commit()
