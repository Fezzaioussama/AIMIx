"""Contracts for pipelines, runs, planning and the model catalogue."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from api.models import PIPELINE_NAME_MAX_LENGTH, STEP_ROLE_MAX_LENGTH, STEP_TITLE_MAX_LENGTH
from api.schemas.common import ModelId, NonBlank
from api.services.catalog import default_model_id


class PipelineStepIn(BaseModel):
    order: int = Field(ge=0)
    # Optional so clients that predate parallel stages keep working: a step
    # without a stage gets its own, which is the old sequential behaviour.
    stage: int | None = Field(None, ge=1)
    title: str = Field("", max_length=STEP_TITLE_MAX_LENGTH)
    role: str = Field("", max_length=STEP_ROLE_MAX_LENGTH)
    allowed_tools: list[NonBlank] | None = None
    is_output: bool = False
    prompt: NonBlank
    model: ModelId

    @field_validator("allowed_tools")
    @classmethod
    def _unique_tools(cls, tools: list[str] | None) -> list[str] | None:
        if tools is not None and len(tools) != len(set(tools)):
            raise ValueError("Each allowed tool must be unique.")
        return tools

    @model_validator(mode="after")
    def _default_stage(self) -> PipelineStepIn:
        if self.stage is None:
            self.stage = self.order
        return self


def _valid_steps(steps: list[PipelineStepIn]) -> list[PipelineStepIn]:
    if not steps:
        raise ValueError("A pipeline needs at least one step.")
    orders = [step.order for step in steps]
    if len(set(orders)) != len(orders):
        raise ValueError("Each step needs a unique order.")
    return steps


Steps = Annotated[list[PipelineStepIn], AfterValidator(_valid_steps)]
PipelineName = Annotated[NonBlank, Field(max_length=PIPELINE_NAME_MAX_LENGTH)]


class PipelineIn(BaseModel):
    """Body of POST and PUT: a whole pipeline."""

    name: PipelineName
    steps: Steps


class PipelinePatch(BaseModel):
    """Body of PATCH: rename and/or replace the steps."""

    name: PipelineName | None = None
    steps: Steps | None = None


class PipelineStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order: int
    stage: int
    title: str
    role: str
    allowed_tools: list[str] | None
    is_output: bool
    prompt: str
    model: str


class PipelineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    user: int = Field(validation_alias="user_id")
    created_at: datetime
    steps: list[PipelineStepOut]

    @field_serializer("created_at")
    def _as_utc(self, value: datetime) -> datetime:
        # SQLite drops the offset; every timestamp is stored in UTC.
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class RunRequest(BaseModel):
    """Contract for POST /api/pipelines/<id>/run."""

    input: NonBlank


class ToolCallOut(BaseModel):
    name: str
    status: Literal["success", "error"]


class StepResultOut(BaseModel):
    step_order: int
    stage: int
    title: str
    model: str
    input_used: str
    output: str
    is_output: bool
    tool_calls: list[ToolCallOut]


class RunResponse(BaseModel):
    pipeline_name: str
    final_output: str
    intermediate_results: list[StepResultOut]


class GenerateRequest(BaseModel):
    """Contract for POST /api/pipelines/generate."""

    description: NonBlank
    planner_model: ModelId | None = None

    @model_validator(mode="after")
    def _default_planner(self) -> GenerateRequest:
        if self.planner_model is None:
            self.planner_model = default_model_id()
        return self


class GenerateResponse(BaseModel):
    generated_pipeline: dict[str, Any]
    available_models: list[str]


class ModelsResponse(BaseModel):
    models: list[str]
    default: str
