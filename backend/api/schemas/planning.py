"""Contracts for planning a pipeline with the planner model: generating one from
a mission, and revising a draft from one sentence. Nothing is saved."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, Field

from api.models import PIPELINE_NAME_MAX_LENGTH
from api.schemas.common import (
    PIPELINE_MAX_STEPS,
    STEP_PROMPT_MAX_LENGTH,
    ModelId,
    NonBlank,
    Trimmed,
)
from api.schemas.pipelines import Inputs, PipelineStepIn, valid_steps
from api.services.pipeline_changes import ChangeKind, ChangeTarget

#: The longest mission a pipeline is planned from.
PLAN_DESCRIPTION_MAX_LENGTH = 20_000


class GenerateRequest(BaseModel):
    """Contract for POST /api/pipelines/generate."""

    description: Annotated[NonBlank, Field(max_length=PLAN_DESCRIPTION_MAX_LENGTH)]
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

    prompt: Annotated[Trimmed, Field(max_length=STEP_PROMPT_MAX_LENGTH)] = ""


class PipelineDraftIn(BaseModel):
    """The pipeline a revision starts from: ``PipelineIn``'s fields, but it may be
    unsaved and unfinished, so its name and step prompts may be blank. Everything
    else is checked as on save."""

    name: Annotated[Trimmed, Field(max_length=PIPELINE_NAME_MAX_LENGTH)] = ""
    inputs: Inputs = Field(default_factory=list)
    steps: Annotated[
        list[DraftStepIn], Field(max_length=PIPELINE_MAX_STEPS), AfterValidator(valid_steps)
    ]


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
