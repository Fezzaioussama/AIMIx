"""Pipeline orchestration: check and run a saved pipeline, and plan a new one
with an LLM. The API records every run through ``services/runs``.

Takes and returns plain Python values — no web-framework request or response
objects (AGENTS.md §2).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from api.exceptions import UpstreamResponseInvalid, ValidationFailed
from api.models import (
    PIPELINE_INPUT_DESCRIPTION_MAX_LENGTH,
    PIPELINE_INPUT_LABEL_MAX_LENGTH,
    PIPELINE_MAX_INPUTS,
    STEP_EXPECTED_OUTPUT_MAX_LENGTH,
    STEP_ROLE_MAX_LENGTH,
    STEP_TITLE_MAX_LENGTH,
    Pipeline,
)
from api.services.agent_types import ToolDescriptor
from api.services.errors import as_domain_error
from api.services.llm import LLMProfile
from api.services.multiagent.conditions import condition_from_data
from api.services.multiagent.contracts import PipelineSpec, RunInputs, RunResult
from api.services.multiagent.contracts import StepAgent as StepGenerator
from api.services.multiagent.graph import GraphPipelineRunner
from api.services.multiagent.mapper import snapshot_pipeline
from api.services.multiagent.reviews import review_from_data
from api.services.pipeline_flow import ensure_valid_spec, flow_problems, flow_step
from api.services.pipeline_inputs import bind_run_inputs, input_name_error
from api.services.plan_prompts import pipeline_generation_prompt
from api.services.plan_questions import Clarification, ClarifyingQuestion, questions_in
from config.settings import get_settings
from llm import exceptions as llm_exceptions
from llm.base import LLMProvider

JSON_OBJECT_PATTERN = re.compile(r"\{[\s\S]*\}")


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
    """Ask the planner model for a pipeline definition and validate the result. When
    it may ask and replies with questions instead, return those (it asks once)."""
    clarification = request.clarification
    prompt = pipeline_generation_prompt(request.description, profile.models, tools, clarification)
    raw = _planner_reply(provider, profile, PlannerCall(prompt, request.planner_model))
    questions = questions_in(_decoded(raw)) if clarification.asking else ()
    if questions:
        return Plan(None, questions)
    return Plan(parse_plan(raw, profile.models, _tool_names(tools)))


def ask_planner(
    provider: LLMProvider,
    profile: LLMProfile,
    call: PlannerCall,
    tools: list[ToolDescriptor] | None = None,
) -> dict[str, Any]:
    """Send one planner prompt and return its plan, sanitised by ``parse_plan``.
    Generation and revision share it, so both fail and clean up alike (§3)."""
    raw = _planner_reply(provider, profile, call)
    return parse_plan(raw, profile.models, _tool_names(tools))


def _planner_reply(provider: LLMProvider, profile: LLMProfile, call: PlannerCall) -> str:
    """The planner model's raw answer to one prompt; a provider failure becomes ours."""
    try:
        return provider.generate(call.prompt, call.model or profile.default_model)
    except llm_exceptions.LLMError as cause:
        raise as_domain_error(cause) from cause


def _tool_names(tools: list[ToolDescriptor] | None) -> list[str] | None:
    return [tool.name for tool in tools] if tools is not None else None


def _decoded(raw: str) -> object:
    """The JSON object a planner reply holds, decoded; failing as ``parse_plan`` does."""
    match = JSON_OBJECT_PATTERN.search(raw or "")
    if match is None:
        raise UpstreamResponseInvalid("The planner did not return a pipeline definition.")
    try:
        return json.loads(match.group())
    except json.JSONDecodeError as cause:
        raise UpstreamResponseInvalid(f"The planner returned invalid JSON: {cause}") from cause


def parse_plan(
    raw: str, available_models: list[str], available_tools: list[str] | None = None
) -> dict[str, Any]:
    """Extract the JSON pipeline from a model response and sanitise it.

    ``available_models`` lists the default first; a step naming any other
    model gets it. Inputs that could not be saved are dropped, and so are the
    conditions and review loops that could not work. Kept separate from the
    call so it can be tested without a provider.
    """
    plan = _decoded(raw)
    if not isinstance(plan, dict) or "name" not in plan or "steps" not in plan:
        raise UpstreamResponseInvalid("The planner returned an incomplete pipeline definition.")

    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        raise UpstreamResponseInvalid("The planner returned a pipeline with no steps.")

    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise UpstreamResponseInvalid("The planner returned a malformed step.")
        sanitise_step(step, index, available_models, available_tools)

    plan["inputs"] = _sanitise_inputs(plan.get("inputs"))
    _drop_unusable_flow(steps, plan["inputs"])
    return plan


def _drop_unusable_flow(steps: list[dict[str, Any]], inputs: list[dict[str, str]]) -> None:
    """Set aside each condition and review loop that cannot work in this plan
    (the checks a save makes): a planner's slip never fails the request, it
    only leaves that step without the field."""
    problems = flow_problems([item["name"] for item in inputs], [flow_step(s) for s in steps])
    for problem in problems:
        steps[problem.order - 1][problem.field] = None  # orders are the positions, from 1


def _text(value: object, limit: int | None = None) -> str:
    """A planner value as trimmed text cut to ``limit``; a non-string becomes ``""``."""
    return value.strip()[:limit] if isinstance(value, str) else ""


def _sanitise_inputs(raw: object) -> list[dict[str, str]]:
    """Keep the planner's inputs that can be saved: objects with a valid name
    that no earlier input took, at most ``PIPELINE_MAX_INPUTS`` of them.

    A name is checked, never shortened, because the prompts refer to it whole.
    """
    inputs: dict[str, dict[str, str]] = {}
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"))
        if input_name_error(name) or name in inputs:
            continue
        inputs[name] = {
            "name": name,
            "label": _text(item.get("label"), PIPELINE_INPUT_LABEL_MAX_LENGTH),
            "description": _text(item.get("description"), PIPELINE_INPUT_DESCRIPTION_MAX_LENGTH),
        }
    return list(inputs.values())[:PIPELINE_MAX_INPUTS]


def sanitise_step(
    step: dict[str, Any],
    index: int,
    available_models: list[str],
    available_tools: list[str] | None,
) -> None:
    """Make a planner step storable: unique order, a valid stage, a known model,
    a short title, role and expected output, a boolean output flag, and a
    condition and review in their stored form (or None). Mission templates
    reuse it, so their steps get models and tools by the same rule.

    ``order`` is renumbered by position because planners that group steps into
    parallel stages tend to repeat it; a missing or invalid stage falls back to
    the step's own position, i.e. sequential.
    """
    step["order"] = index
    stage = step.get("stage")
    if isinstance(stage, bool) or not isinstance(stage, int) or stage < 1:
        step["stage"] = index
    if step.get("model") not in available_models:
        step["model"] = available_models[0] if available_models else ""
    step["title"] = _text(step.get("title"), STEP_TITLE_MAX_LENGTH)
    step["role"] = _text(step.get("role"), STEP_ROLE_MAX_LENGTH)
    step["expected_output"] = _text(step.get("expected_output"), STEP_EXPECTED_OUTPUT_MAX_LENGTH)
    selected = step.get("allowed_tools")
    if isinstance(selected, list) and available_tools is not None:
        step["allowed_tools"] = list(
            dict.fromkeys(
                name for name in selected if isinstance(name, str) and name in available_tools
            )
        )
    else:
        step["allowed_tools"] = None
    step["is_output"] = step.get("is_output") is True
    condition, review = (
        condition_from_data(step.get("condition")),
        review_from_data(step.get("review")),
    )
    step["condition"] = None if condition is None else asdict(condition)
    step["review"] = None if review is None else asdict(review)


def ensure_runnable(pipeline: Pipeline) -> None:
    """Guard against running a pipeline that has no steps."""
    if not pipeline.steps:
        raise ValidationFailed("This pipeline has no steps to run.")
