"""Pipeline orchestration: check and run a saved pipeline, and plan a new one
with an LLM. The API records every run through ``services/runs``.

Takes and returns plain Python values — no web-framework request or response
objects (AGENTS.md §2).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, TypeVar

from api.exceptions import UpstreamResponseInvalid, ValidationFailed
from api.models import Pipeline
from api.services.agent_types import ToolDescriptor
from api.services.errors import as_domain_error
from api.services.final_check import with_final_check
from api.services.llm import LLMProfile
from api.services.multiagent.contracts import PipelineSpec, RunInputs, RunResult
from api.services.multiagent.contracts import StepAgent as StepGenerator
from api.services.multiagent.graph import GraphPipelineRunner
from api.services.multiagent.mapper import snapshot_pipeline
from api.services.pipeline_flow import ensure_valid_spec
from api.services.pipeline_inputs import bind_run_inputs
from api.services.plan_parsing import decoded, on_default_model, parse_plan
from api.services.plan_prompts import pipeline_generation_prompt
from api.services.plan_questions import Clarification, ClarifyingQuestion, questions_in
from config.settings import get_settings
from llm import exceptions as llm_exceptions
from llm.base import LLMProvider

logger = logging.getLogger(__name__)
_Reply = TypeVar("_Reply")


@dataclass(frozen=True)
class PreparedRun:
    """A run checked and ready to execute: the pipeline's snapshot and its inputs."""

    spec: PipelineSpec
    inputs: RunInputs


def prepare_run(
    pipeline: Pipeline, initial_input: str = "", values: Mapping[str, str] | None = None
) -> PreparedRun:
    """Snapshot a saved pipeline and check it, and a run's free text (or its value
    for each named input the pipeline declares), before any agent starts (§6)."""
    ensure_runnable(pipeline)
    spec = snapshot_pipeline(pipeline)
    ensure_valid_spec(spec)
    return PreparedRun(spec, bind_run_inputs(spec.inputs, initial_input, values or {}))


def run(
    pipeline: Pipeline,
    generator: StepGenerator,
    initial_input: str = "",
    values: Mapping[str, str] | None = None,
) -> RunResult:
    """Run a saved pipeline in-process and unrecorded (tests, one-off tools);
    LangGraph owns the multiagent execution."""
    prepared = prepare_run(pipeline, initial_input, values)
    return GraphPipelineRunner(get_settings().pipeline_max_parallel_steps).run(
        prepared.spec, generator, prepared.inputs
    )


@dataclass(frozen=True)
class PlanRequest:
    """What to plan; no ``planner_model`` means the profile's default model. The
    ``clarification`` says whether the planner may ask questions first (Missions),
    and holds the answers to the ones it asked."""

    description: str
    planner_model: str | None = None
    clarification: Clarification = field(default_factory=Clarification)


@dataclass(frozen=True)
class Plan:
    """What a generation gave: a pipeline, or else the questions to answer first."""

    pipeline: dict[str, Any] | None
    questions: tuple[ClarifyingQuestion, ...] = ()


@dataclass(frozen=True)
class PlannerCall:
    """One planner request: its rendered prompt, and the model to ask; no
    ``model`` means the profile's default model."""

    prompt: str
    model: str | None = None


def generate(
    provider: LLMProvider,
    profile: LLMProfile,
    request: PlanRequest,
    tools: list[ToolDescriptor] | None = None,
) -> Plan:
    """Ask the planner model for a pipeline definition and validate the result; its
    steps run on the default model unless the request names another, and a plan
    without a reviewer gets the final check. When the planner may ask and replies
    with questions instead, return those (it asks once)."""
    clarification = request.clarification
    prompt = pipeline_generation_prompt(request.description, profile.models, tools, clarification)
    call = PlannerCall(prompt, request.planner_model)

    def ask() -> Plan:
        raw = _planner_reply(provider, profile, call)
        questions = questions_in(decoded(raw)) if clarification.asking else ()
        if questions:
            return Plan(None, questions)
        return Plan(parse_plan(raw, profile.models, _tool_names(tools)))

    answer = _asked_twice_at_most(ask)
    plan = answer.pipeline
    if plan is None:
        return answer
    asked = " ".join([request.description, *(item.answer for item in clarification.answers)])
    on_default_model(plan["steps"], profile.default_model, asked)
    with_final_check(plan, request.description, clarification.answers, profile.default_model)
    return Plan(plan)


def ask_planner(
    provider: LLMProvider,
    profile: LLMProfile,
    call: PlannerCall,
    tools: list[ToolDescriptor] | None = None,
) -> dict[str, Any]:
    """Send one planner prompt and return its plan, sanitised by ``parse_plan``.
    Generation and revision share it, so both fail and clean up alike (§3)."""
    names = _tool_names(tools)
    return _asked_twice_at_most(
        lambda: parse_plan(_planner_reply(provider, profile, call), profile.models, names)
    )


def _asked_twice_at_most(ask: Callable[[], _Reply]) -> _Reply:
    """The planner's answer, asked for once more when it cannot be used (not JSON, or no
    whole pipeline): models slip now and then, and one slip must not stop a mission."""
    try:
        return ask()
    except UpstreamResponseInvalid as cause:
        logger.warning("pipeline.plan_retry reason=%s", cause.detail)
        return ask()


def _planner_reply(provider: LLMProvider, profile: LLMProfile, call: PlannerCall) -> str:
    """The planner model's raw answer to one prompt; a provider failure becomes ours."""
    try:
        return provider.generate(call.prompt, call.model or profile.default_model)
    except llm_exceptions.LLMError as cause:
        raise as_domain_error(cause) from cause


def _tool_names(tools: list[ToolDescriptor] | None) -> list[str] | None:
    return [tool.name for tool in tools] if tools is not None else None


def ensure_runnable(pipeline: Pipeline) -> None:
    """Guard against running a pipeline that has no steps."""
    if not pipeline.steps:
        raise ValidationFailed("This pipeline has no steps to run.")
