"""What runs used and cost: a run's totals, and one user's report over a period.

Totals are computed from the run steps, never stored. A step row is the one
place a model call's usage is written (``RunRecorder.record_usage``), so a
run's total can never disagree with its steps, and a step that failed or was
stopped still counts what it spent.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy.orm import Session

from api.models import User
from api.repositories import usage as repository
from api.repositories.usage import StepUsageRow
from llm.usage import TokenUsage, total


class UsageRecord(Protocol):
    """Anything that carries one step's usage: a run step row, or its schema."""

    @property
    def input_tokens(self) -> int: ...

    @property
    def output_tokens(self) -> int: ...

    @property
    def cost_usd(self) -> float | None: ...


def step_usage(step: UsageRecord) -> TokenUsage:
    return TokenUsage.of(step.input_tokens, step.output_tokens, step.cost_usd)


def total_usage(steps: Iterable[UsageRecord]) -> TokenUsage:
    """Steps' usage added up: the known costs summed, and ``cost_complete``
    False when a step that used tokens has no known cost."""
    return total(step_usage(step) for step in steps)


@dataclass(frozen=True)
class PipelineUsage:
    """What one pipeline's runs used; a deleted pipeline keeps its last name."""

    pipeline_id: int | None
    pipeline_name: str
    runs: int
    usage: TokenUsage


@dataclass(frozen=True)
class UsageReport:
    """What a user's runs started in the last ``days`` days used (§7 DTO)."""

    days: int
    since: datetime
    runs: int
    usage: TokenUsage
    #: Costliest first.
    pipelines: list[PipelineUsage]


def usage_report(
    session: Session, user: User, days: int, now: datetime | None = None
) -> UsageReport:
    """``user``'s usage over the ``days`` days before ``now``, in all and per pipeline."""
    since = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    rows = repository.steps_since(session, user, since)
    return UsageReport(days, since, _run_count(rows), total_usage(rows), _by_pipeline(rows))


def _run_count(rows: Iterable[StepUsageRow]) -> int:
    return len({row.run_id for row in rows})


def _pipeline_key(row: StepUsageRow) -> int | str:
    """A pipeline by its id; a deleted one, which has none any more, by its name."""
    return row.pipeline_id if row.pipeline_id is not None else f"deleted:{row.pipeline_name}"


def _costliest_first(entry: PipelineUsage) -> tuple[float, int]:
    return -(entry.usage.cost_usd or 0.0), -entry.usage.total_tokens


def _by_pipeline(rows: list[StepUsageRow]) -> list[PipelineUsage]:
    groups: dict[int | str, list[StepUsageRow]] = {}
    for row in rows:
        groups.setdefault(_pipeline_key(row), []).append(row)
    # Rows come oldest run first, so a group's last row has the latest name.
    entries = [
        PipelineUsage(
            group[-1].pipeline_id, group[-1].pipeline_name, _run_count(group), total_usage(group)
        )
        for group in groups.values()
    ]
    return sorted(entries, key=_costliest_first)
