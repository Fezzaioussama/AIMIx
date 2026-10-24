"""Pipeline orchestration: run a saved pipeline, and plan a new one with an LLM.

Takes and returns plain Python values — no web-framework request or response
objects (AGENTS.md §2).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
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
from api.services.multiagent.contracts import RunResult
from api.services.multiagent.contracts import StepAgent as StepGenerator
from api.services.multiagent.graph import GraphPipelineRunner
from api.services.multiagent.mapper import snapshot_pipeline
from api.services.pipeline_inputs import bind_run_inputs, input_name_error
from api.services.prompts import pipeline_generation_prompt
from config.settings import get_settings
from llm import exceptions as llm_exceptions
from llm.base import LLMProvider

JSON_OBJECT_PATTERN = re.compile(r"\{[\s\S]*\}")


def run(
    pipeline: Pipeline,
    generator: StepGenerator,
    initial_input: str = "",
    values: Mapping[str, str] | None = None,
) -> RunResult:
    """Run a saved pipeline on free text, or on a value for each named input it
    declares. The inputs are checked before any agent starts; LangGraph owns
    the multiagent execution."""
    spec = snapshot_pipeline(pipeline)
    inputs = bind_run_inputs(spec.inputs, initial_input, values or {})
    return GraphPipelineRunner(get_settings().pipeline_max_parallel_steps).run(
        spec, generator, inputs
    )


@dataclass(frozen=True)
class PlanRequest:
    """What to plan; no ``planner_model`` means the profile's default model."""

    description: str
    planner_model: str | None = None


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
) -> dict[str, Any]:
    """Ask the planner model for a pipeline definition and validate the result."""
    prompt = pipeline_generation_prompt(request.description, profile.models, tools)
    return ask_planner(provider, profile, PlannerCall(prompt, request.planner_model), tools)


def ask_planner(
    provider: LLMProvider,
    profile: LLMProfile,
    call: PlannerCall,
    tools: list[ToolDescriptor] | None = None,
) -> dict[str, Any]:
    """Send one planner prompt and return its plan, sanitised by ``parse_plan``.
    Generation and revision share it, so both fail and clean up alike (§3)."""
    try:
        raw = provider.generate(call.prompt, call.model or profile.default_model)
    except llm_exceptions.LLMError as cause:
        raise as_domain_error(cause) from cause

    names = [tool.name for tool in tools] if tools is not None else None
    return parse_plan(raw, profile.models, names)


def parse_plan(
    raw: str, available_models: list[str], available_tools: list[str] | None = None
) -> dict[str, Any]:
    """Extract the JSON pipeline from a model response and sanitise it.

    ``available_models`` lists the default first; a step naming any other
    model gets it. Inputs that could not be saved are dropped. Kept separate
    from the call so it can be tested without a provider.
    """
    match = JSON_OBJECT_PATTERN.search(raw or "")
    if match is None:
        raise UpstreamResponseInvalid("The planner did not return a pipeline definition.")

    try:
        plan = json.loads(match.group())
    except json.JSONDecodeError as cause:
        raise UpstreamResponseInvalid(f"The planner returned invalid JSON: {cause}") from cause

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
    return plan


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
    a short title, role and expected output, and a boolean output flag. Mission
    templates reuse it, so their steps get models and tools by the same rule.

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


def ensure_runnable(pipeline: Pipeline) -> None:
    """Guard against running a pipeline that has no steps."""
    if not pipeline.steps:
        raise ValidationFailed("This pipeline has no steps to run.")
