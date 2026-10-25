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
from api.schemas.common import ModelId, NonBlank, UtcDateTime
from api.schemas.usage import BudgetIn
from api.services.multiagent.conditions import StepCondition, shape_problem, tidy
from api.services.multiagent.reviews import rounds_problem
from api.services.pipeline_changes import ChangeKind, ChangeTarget
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


class StepConditionIn(BaseModel):
    """ "Run this step only if ...": what to look at, how to compare it, and with
    what. Whether its source exists in the pipeline is checked as a whole
    (``services/pipeline_flow``), when the pipeline is saved."""

    source: Annotated[str, StringConstraints(strip_whitespace=True)]
    operator: Annotated[str, StringConstraints(strip_whitespace=True)]
    value: str = ""

    @model_validator(mode="after")
    def _usable(self) -> StepConditionIn:
        condition = tidy(StepCondition(self.source, self.operator, self.value))
        if problem := shape_problem(condition):
            raise ValueError(f"A step's condition {problem}.")
        self.value = condition.value
        return self


def _valid_rounds(max_rounds: int) -> int:
    if problem := rounds_problem(max_rounds):
        raise ValueError(f"A review loop {problem}.")
    return max_rounds


class StepReviewIn(BaseModel):
    """Makes a step a reviewer that can send the work back for fixes. That the
    stage is an earlier one that exists is checked as a whole, when the pipeline
    is saved."""

    send_back_to_stage: int = Field(ge=1)
    max_rounds: Annotated[int, AfterValidator(_valid_rounds)]


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
    condition: StepConditionIn | None = None
    review: StepReviewIn | None = None

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


class StepConditionOut(BaseModel):
    source: str
    operator: str
    value: str


class StepReviewOut(BaseModel):
    send_back_to_stage: int
    max_rounds: int


class StepDefinitionOut(BaseModel):
    """A step as saved: in a pipeline, or in the snapshot a run executes. A run
    saved before conditions and review loops existed has neither: both are null."""

    model_config = ConfigDict(from_attributes=True)

    order: int
    stage: int
    title: str
    role: str
    allowed_tools: list[str] | None
    is_output: bool
    expected_output: str
    prompt: str
    model: str
    condition: StepConditionOut | None = None
    review: StepReviewOut | None = None


class PipelineStepOut(StepDefinitionOut):
    id: int


class PipelineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    user: int = Field(validation_alias="user_id")
    created_at: UtcDateTime
    inputs: list[PipelineInputField]
    steps: list[PipelineStepOut]


Trimmed = Annotated[str, StringConstraints(strip_whitespace=True)]


class RunRequest(BudgetIn):
    """Contract for POST /api/pipelines/<id>/run.

    ``input`` is the free text a pipeline without named inputs runs on;
    ``inputs`` holds a value for each input a pipeline declares. Which one is
    required depends on the pipeline, so the service checks them. The optional
    spending limits (``BudgetIn``) stop the run once reached.
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
    #: Its condition did not hold, so it did not run.
    skipped: bool = False
    #: The review round it belongs to; above 1 when a review loop redid it.
    rounds: int = 1


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


#: The longest change request a revision accepts: a few sentences.
REVISION_INSTRUCTION_MAX_LENGTH = 2000


class DraftStepIn(PipelineStepIn):
    """A step of a draft under revision: unlike a saved step, its prompt may
    still be blank (the planner writes it)."""

    prompt: Trimmed = ""


class PipelineDraftIn(BaseModel):
    """The pipeline a revision starts from: ``PipelineIn``'s fields, but it may be
    unsaved and unfinished, so its name and step prompts may be blank. Everything
    else is checked as on save."""

    name: Annotated[Trimmed, Field(max_length=PIPELINE_NAME_MAX_LENGTH)] = ""
    inputs: Inputs = Field(default_factory=list)
    steps: Annotated[list[DraftStepIn], AfterValidator(_valid_steps)]


class ReviseRequest(BaseModel):
    """Contract for POST /api/pipelines/revise. Nothing is saved."""

    pipeline: PipelineDraftIn
    instruction: Annotated[NonBlank, Field(max_length=REVISION_INSTRUCTION_MAX_LENGTH)]
    #: Omitted means the caller's default model.
    planner_model: ModelId | None = None


class PipelineChangeOut(BaseModel):
    """One difference between the draft and its revision, for people to review."""

    target: ChangeTarget
    kind: ChangeKind
    label: str
    order: int | None
    fields: list[str]


class ReviseResponse(BaseModel):
    revised_pipeline: dict[str, Any]
    changes: list[PipelineChangeOut]
    available_models: list[str]


class ModelsResponse(BaseModel):
    models: list[str]
    default: str
