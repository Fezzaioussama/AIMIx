"""Data access for usage reports (AGENTS.md §7 Repository).

Ownership filtering lives here: a report only ever reads the user's own runs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, and_, case, func, select
from sqlalchemy.orm import Session

from api.models import Run, RunStep, UsageEvent, UsageKind, User
from llm.usage import TokenUsage


@dataclass(frozen=True)
class StepUsageRow:
    """One run step's usage, with the run and pipeline it belongs to."""

    run_id: int
    pipeline_id: int | None
    pipeline_name: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None


def _as_stored(moment: datetime) -> datetime:
    """Timestamps are stored as naive UTC; compare like with like."""
    return moment.astimezone(timezone.utc).replace(tzinfo=None) if moment.tzinfo else moment


def steps_since(session: Session, user: User, since: datetime) -> list[StepUsageRow]:
    """The steps of ``user``'s runs started (created) at or after ``since``,
    oldest run first, so the last row of a pipeline carries its latest name."""
    stored_since = _as_stored(since)
    statement = (
        select(
            Run.id,
            Run.pipeline_id,
            Run.pipeline_name,
            RunStep.input_tokens,
            RunStep.output_tokens,
            RunStep.cost_usd,
        )
        .join(RunStep, RunStep.run_id == Run.id)
        .where(Run.user_id == user.id, Run.created_at >= stored_since)
        .order_by(Run.created_at, Run.id, RunStep.step_order)
    )
    return [StepUsageRow(*row) for row in session.execute(statement)]


@dataclass(frozen=True)
class NewUsageEvent:
    """One model call made outside a run (a chat message's, the planner's), to keep."""

    user_id: int
    kind: UsageKind
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None


def record_event(session: Session, new: NewUsageEvent) -> None:
    session.add(UsageEvent(**asdict(new)))
    session.commit()


def events_since(session: Session, user: User, since: datetime) -> list[UsageEvent]:
    """``user``'s chat and planner calls made at or after ``since``, oldest first."""
    statement = (
        select(UsageEvent)
        .where(UsageEvent.user_id == user.id, UsageEvent.created_at >= _as_stored(since))
        .order_by(UsageEvent.created_at, UsageEvent.id)
    )
    return list(session.scalars(statement))


def _sums(table: type[RunStep] | type[UsageEvent]) -> tuple[Any, ...]:
    """Input tokens, output tokens, the known cost, and how many of the table's rows
    used tokens at an unknown cost."""
    unpriced = and_(table.cost_usd.is_(None), (table.input_tokens + table.output_tokens) > 0)
    return (
        func.coalesce(func.sum(table.input_tokens), 0),
        func.coalesce(func.sum(table.output_tokens), 0),
        func.sum(table.cost_usd),
        func.coalesce(func.sum(case((unpriced, 1), else_=0)), 0),
    )


def _totals(session: Session, statement: Select[Any]) -> TokenUsage:
    input_tokens, output_tokens, cost, unpriced = session.execute(statement).one()
    return TokenUsage(int(input_tokens), int(output_tokens), cost, unpriced == 0)


def spent_since(session: Session, user_id: int, since: datetime) -> TokenUsage:
    """What ``user_id``'s runs created at or after ``since``, and the chat and planner
    calls made since then, used, as one usage: the day's spending, summed in the
    database."""
    stored = _as_stored(since)
    steps = (
        select(*_sums(RunStep))
        .join(Run, Run.id == RunStep.run_id)
        .where(Run.user_id == user_id, Run.created_at >= stored)
    )
    events = select(*_sums(UsageEvent)).where(
        UsageEvent.user_id == user_id, UsageEvent.created_at >= stored
    )
    return _totals(session, steps) + _totals(session, events)
