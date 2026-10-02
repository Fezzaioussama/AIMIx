"""Pipeline orchestration: run a saved pipeline, and plan a new one with an LLM.

Takes and returns plain Python values — no web-framework request or response
objects (AGENTS.md §2).
"""

from __future__ import annotations

import json
import re
from typing import Any

from api.exceptions import UpstreamResponseInvalid, ValidationFailed
from api.models import STEP_ROLE_MAX_LENGTH, STEP_TITLE_MAX_LENGTH, Pipeline
from api.services.agent_types import ToolDescriptor
from api.services.catalog import available_model_ids, default_model_id
from api.services.errors import as_domain_error
from api.services.multiagent.contracts import RunResult
from api.services.multiagent.contracts import StepAgent as StepGenerator
from api.services.multiagent.graph import GraphPipelineRunner
from api.services.multiagent.mapper import snapshot_pipeline
from api.services.prompts import pipeline_generation_prompt
from config.settings import get_settings
from llm import exceptions as llm_exceptions
from llm.base import LLMProvider

JSON_OBJECT_PATTERN = re.compile(r"\{[\s\S]*\}")


def run(pipeline: Pipeline, generator: StepGenerator, initial_input: str) -> RunResult:
    """Keep the existing service API while LangGraph owns multiagent execution."""
    return GraphPipelineRunner(get_settings().pipeline_max_parallel_steps).run(
        snapshot_pipeline(pipeline), generator, initial_input
    )


def generate(
    provider: LLMProvider,
    description: str,
    planner_model: str,
    tools: list[ToolDescriptor] | None = None,
) -> dict[str, Any]:
    """Ask the planner model for a pipeline definition and validate the result."""
    models = available_model_ids()
    prompt = pipeline_generation_prompt(description, models, tools)

    try:
        raw = provider.generate(prompt, planner_model)
    except llm_exceptions.LLMError as cause:
        raise as_domain_error(cause) from cause

    return parse_plan(raw, models, [tool.name for tool in tools] if tools is not None else None)


def parse_plan(
    raw: str, available_models: list[str], available_tools: list[str] | None = None
) -> dict[str, Any]:
    """Extract the JSON pipeline from a model response and sanitise its models.

    Kept separate from the call so it can be tested without a provider.
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
        _sanitise_step(step, index, available_models, available_tools)

    return plan


def _sanitise_step(
    step: dict[str, Any],
    index: int,
    available_models: list[str],
    available_tools: list[str] | None,
) -> None:
    """Make a planner step storable: unique order, a valid stage, a known model,
    a short title and a boolean output flag.

    ``order`` is renumbered by position because planners that group steps into
    parallel stages tend to repeat it; a missing or invalid stage falls back to
    the step's own position, i.e. sequential.
    """
    step["order"] = index
    stage = step.get("stage")
    if isinstance(stage, bool) or not isinstance(stage, int) or stage < 1:
        step["stage"] = index
    if step.get("model") not in available_models:
        step["model"] = default_model_id()
    title = step.get("title")
    step["title"] = title.strip()[:STEP_TITLE_MAX_LENGTH] if isinstance(title, str) else ""
    role = step.get("role")
    step["role"] = role.strip()[:STEP_ROLE_MAX_LENGTH] if isinstance(role, str) else ""
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
