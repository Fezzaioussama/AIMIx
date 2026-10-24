"""Contracts for pipelines, runs, planning and the model catalogue."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from api.models import (
    PIPELINE_INPUT_DESCRIPTION_MAX_LENGTH,
    PIPELINE_INPUT_LABEL_MAX_LENGTH,
    PIPELINE_MAX_INPUTS,
    PIPELINE_NAME_MAX_LENGTH,
    STEP_EXPECTED_OUTPUT_MAX_LENGTH,
    STEP_ROLE_MAX_LENGTH,
    STEP_TITLE_MAX_LENGTH,
)
from api.schemas.common import ModelId, NonBlank, UtcDatetime
from api.services.pipeline_inputs import input_name_error


def _valid_input_name(name: str) -> str:
    if error := input_name_error(name):
        raise ValueError(error)
    return name


InputName = Annotated[
    str, StringConstraints(strip_whitespace=True), AfterValidator(_valid_input_name)
]


class PipelineInputField(BaseModel):
    """A named value every run is given; step prompts insert it as ``{name}``."""

    name: InputName
    label: str = Field("", max_length=PIPELINE_INPUT_LABEL_MAX_LENGTH)
    description: str = Field("", max_length=PIPELINE_INPUT_DESCRIPTION_MAX_LENGTH)


def _unique_inputs(inputs: list[PipelineInputField]) -> list[PipelineInputField]:
    names = [field.name for field in inputs]
    if len(set(names)) != len(names):
        raise ValueError("Each input needs a unique name.")
    return inputs


Inputs = Annotated[
    list[PipelineInputField],
    Field(max_length=PIPELINE_MAX_INPUTS),
    AfterValidator(_unique_inputs),
]


class PipelineStepIn(BaseModel):
    order: int = Field(ge=0)
    # Optional so clients that predate parallel stages keep working: a step
    # without a stage gets its own, which is the old sequential behaviour.
    stage: int | None = Field(None, ge=1)
    title: str = Field("", max_length=STEP_TITLE_MAX_LENGTH)
    role: str = Field("", max_length=STEP_ROLE_MAX_LENGTH)
    allowed_tools: list[NonBlank] | None = None
    is_output: bool = False
    expected_output: str = Field("", max_length=STEP_EXPECTED_OUTPUT_MAX_LENGTH)
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
    """Body of POST and PUT: a whole pipeline. Omitting ``inputs`` declares
    none, so the pipeline runs on one free-text input."""

    name: PipelineName
    inputs: Inputs = Field(default_factory=list)
    steps: Steps


class PipelinePatch(BaseModel):
    """Body of PATCH: rename, redeclare the inputs and/or replace the steps."""

    name: PipelineName | None = None
    inputs: Inputs | None = None
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
    expected_output: str
    prompt: str
    model: str


class PipelineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    user: int = Field(validation_alias="user_id")
    created_at: UtcDatetime
    inputs: list[PipelineInputField]
    steps: list[PipelineStepOut]


Trimmed = Annotated[str, StringConstraints(strip_whitespace=True)]


class RunRequest(BaseModel):
    """Contract for POST /api/pipelines/<id>/run.

    ``input`` is the free text a pipeline without named inputs runs on;
    ``inputs`` holds a value for each input a pipeline declares. Which one is
    required depends on the pipeline, so the service checks them.
    """

    input: Trimmed = ""
    inputs: dict[str, Trimmed] = Field(default_factory=dict)


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
    #: Omitted means the caller's default model.
    planner_model: ModelId | None = None


class GenerateResponse(BaseModel):
    generated_pipeline: dict[str, Any]
    available_models: list[str]


class ModelsResponse(BaseModel):
    models: list[str]
    default: str
