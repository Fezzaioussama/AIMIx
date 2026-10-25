"""Contracts for token usage and cost: totals, spending limits, and GET /api/usage."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.common import UtcDateTime
from api.services.run_budget import RunBudget

#: GET /api/usage covers this many days by default, and at most the maximum.
USAGE_DEFAULT_DAYS = 30
USAGE_MAX_DAYS = 366


class UsageOut(BaseModel):
    """Tokens and cost of model calls: a run's, a pipeline's or a period's."""

    model_config = ConfigDict(from_attributes=True)

    input_tokens: int
    output_tokens: int
    #: USD, the known costs added up; null when none is known.
    cost_usd: float | None
    #: False when some tokens came from a model whose cost is unknown.
    cost_complete: bool


class BudgetIn(BaseModel):
    """Spending limits a request may set; a limit left out keeps its default."""

    #: Stop once the model calls have cost this much (USD).
    max_cost_usd: float | None = Field(None, gt=0, allow_inf_nan=False)
    #: Stop once the model calls have used this many tokens (in and out).
    max_tokens: int | None = Field(None, ge=1)

    @property
    def budget(self) -> RunBudget:
        return RunBudget(self.max_cost_usd, self.max_tokens)


class UsageQuery(BaseModel):
    """Query of GET /api/usage: how many days back to count."""

    days: int = Field(USAGE_DEFAULT_DAYS, ge=1, le=USAGE_MAX_DAYS)


class PipelineUsageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    #: null once the pipeline was deleted; its runs keep its name.
    pipeline_id: int | None
    pipeline_name: str
    runs: int
    usage: UsageOut


class UsageReportOut(BaseModel):
    """What the user's runs started in the last ``days`` days used."""

    model_config = ConfigDict(from_attributes=True)

    days: int
    since: UtcDateTime
    runs: int
    usage: UsageOut
    #: Costliest first.
    pipelines: list[PipelineUsageOut]
