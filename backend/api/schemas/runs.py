"""Contracts for pipeline runs: the run and its steps, and the history page."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, computed_field

from api.models import RunStatus, RunTrigger, StepStatus
from api.schemas.common import UtcDateTime
from api.schemas.pipelines import PipelineInputField, StepDefinitionOut, ToolCallOut

#: Runs per history page: the default, and the most one request may ask for.
RUN_PAGE_DEFAULT_LIMIT = 20
RUN_PAGE_MAX_LIMIT = 100


class RunListQuery(BaseModel):
    """Query of GET /api/runs: one page, newest first, optionally of one pipeline."""

    limit: int = Field(RUN_PAGE_DEFAULT_LIMIT, ge=1, le=RUN_PAGE_MAX_LIMIT)
    offset: int = Field(0, ge=0)
    pipeline_id: int | None = None


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


class RunStepOut(_Failure):
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
    #: What started it; ``schedule_id`` is null once that schedule is deleted.
    trigger: RunTrigger
    schedule_id: int | None
    status: RunStatus
    created_at: UtcDateTime
    started_at: UtcDateTime | None
    finished_at: UtcDateTime | None


class RunOut(RunSummaryOut):
    """A whole run: what it was given, its steps so far, and its result."""

    input: str = Field(validation_alias="input_text")
    inputs: dict[str, str] = Field(validation_alias="input_values")
    final_output: str
    definition: RunDefinitionOut
    steps: list[RunStepOut]


class RunPageOut(BaseModel):
    items: list[RunSummaryOut]
    #: How many runs match in all, for paging.
    total: int
