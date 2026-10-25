"""Data access for usage reports (AGENTS.md §7 Repository).

Ownership filtering lives here: a report only ever reads the user's own runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models import Run, RunStep, User


@dataclass(frozen=True)
class StepUsageRow:
    """One run step's usage, with the run and pipeline it belongs to."""

    run_id: int
    pipeline_id: int | None
    pipeline_name: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None


def steps_since(session: Session, user: User, since: datetime) -> list[StepUsageRow]:
    """The steps of ``user``'s runs started (created) at or after ``since``,
    oldest run first, so the last row of a pipeline carries its latest name."""
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
        .where(Run.user_id == user.id, Run.created_at >= since)
        .order_by(Run.created_at, Run.id, RunStep.step_order)
    )
    return [StepUsageRow(*row) for row in session.execute(statement)]
