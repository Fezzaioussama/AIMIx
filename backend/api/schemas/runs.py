"""Contracts for pipeline runs: the run and its steps, and the history page."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, computed_field

from api.models import RunStatus, StepStatus
from api.schemas.approvals import RunApprovalOut
from api.schemas.common import UtcDateTime
from api.schemas.pipelines import PipelineInputField, StepDefinitionOut, ToolCallOut
from api.schemas.usage import BudgetIn, UsageOut
from api.services.usage import total_usage

#: Runs per history page: the default, and the most one request may ask for.
RUN_PAGE_DEFAULT_LIMIT = 20
RUN_PAGE_MAX_LIMIT = 100


class RunListQuery(BaseModel):
    """Query of GET /api/runs: one page, newest first, optionally of one
    pipeline or one status (``?status=waiting&limit=1`` counts what waits for you)."""

    limit: int = Field(RUN_PAGE_DEFAULT_LIMIT, ge=1, le=RUN_PAGE_MAX_LIMIT)
    offset: int = Field(0, ge=0)
    pipeline_id: int | None = None
    status: RunStatus | None = None


class RunErrorOut(BaseModel):
    code: str
    detail: str


class _Failure(BaseModel):
    """Reads the stored error columns and sends them as one ``error`` object
    (null when there was none)."""

    model_config = ConfigDict(from_attributes=True)

    error_code: str = Field(exclude=True)
    error_detail: str = Field(exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def error(self) -> RunErrorOut | None:
        if not self.error_code:
            return None
        return RunErrorOut(code=self.error_code, detail=self.error_detail)


class _StepUsage(BaseModel):
    """What a step's model calls used, over every attempt."""

    model_config = ConfigDict(from_attributes=True)

    input_tokens: int = 0
    output_tokens: int = 0
    #: USD; null when the cost of its model is unknown.
    cost_usd: float | None = None


class RunStepOut(_Failure, _StepUsage):
    step_order: int
    stage: int
    title: str
    model: str
    status: StepStatus
    input_used: str
    output: str
    is_output: bool
    tool_calls: list[ToolCallOut]
    started_at: UtcDateTime | None
    finished_at: UtcDateTime | None


class RunDefinitionOut(BaseModel):
    """The pipeline as it was when the run started."""

    name: str
    inputs: list[PipelineInputField]
    steps: list[StepDefinitionOut]


class RunSummaryOut(_Failure):
    """A run in the history list: no inputs, outputs or steps."""

    id: int
    pipeline_id: int | None
    pipeline_name: str
    status: RunStatus
    created_at: UtcDateTime
    started_at: UtcDateTime | None
    finished_at: UtcDateTime | None
    #: Spending limits; null is no limit.
    max_cost_usd: float | None = None
    max_tokens: int | None = None
    #: Read to add up the run's usage; a summary does not list its steps.
    steps: Sequence[_StepUsage] = Field(default=(), exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def usage(self) -> UsageOut:
        """What the run's model calls used and cost so far, over every attempt."""
        return UsageOut.model_validate(total_usage(self.steps))


class RunOut(RunSummaryOut):
    """A whole run: what it was given, its steps so far, and its result."""

    input: str = Field(validation_alias="input_text")
    inputs: dict[str, str] = Field(validation_alias="input_values")
    final_output: str
    definition: RunDefinitionOut
    steps: list[RunStepOut]
    #: Tool calls waiting for your answer, oldest first (approval gates).
    pending_approvals: list[RunApprovalOut]


class RunPageOut(BaseModel):
    items: list[RunSummaryOut]
    #: How many runs match in all, for paging.
    total: int


class ResumeRequest(BudgetIn):
    """Optional body of POST /api/runs/<id>/resume: new spending limits; a limit
    left out stays as it was."""
