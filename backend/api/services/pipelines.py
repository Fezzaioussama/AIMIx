"""Pipeline orchestration: run a saved pipeline, and plan a new one with an LLM.

Takes and returns plain Python values — no Django request or response objects
(AGENTS.md §2).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from api.exceptions import UpstreamResponseInvalid, ValidationFailed
from api.models import Pipeline
from api.services.catalog import available_model_ids, default_model_id
from api.services.errors import as_domain_error
from api.services.prompts import pipeline_generation_prompt, step_prompt
from llm import exceptions as llm_exceptions
from llm.base import LLMProvider

logger = logging.getLogger(__name__)

JSON_OBJECT_PATTERN = re.compile(r"\{[\s\S]*\}")


@dataclass(frozen=True)
class StepResult:
    """One executed step (§7 DTO)."""

    step_order: int
    model: str
    input_used: str
    output: str


@dataclass(frozen=True)
class RunResult:
    pipeline_name: str
    final_output: str
    intermediate_results: list[StepResult]


def run(pipeline: Pipeline, provider: LLMProvider, initial_input: str) -> RunResult:
    """Execute every step in order, feeding each output into the next."""
    current = initial_input
    results: list[StepResult] = []
    started = perf_counter()

    for step in pipeline.steps.all():
        try:
            output = provider.generate(step_prompt(step.prompt, current), step.model)
        except llm_exceptions.LLMError as cause:
            raise as_domain_error(cause) from cause

        results.append(
            StepResult(step_order=step.order, model=step.model, input_used=current, output=output)
        )
        current = output

    logger.info(
        "pipeline.run pipeline_id=%s steps=%s duration_ms=%.0f",
        pipeline.pk,
        len(results),
        (perf_counter() - started) * 1000,
    )
    return RunResult(
        pipeline_name=pipeline.name, final_output=current, intermediate_results=results
    )


def generate(provider: LLMProvider, description: str, planner_model: str) -> dict[str, Any]:
    """Ask the planner model for a pipeline definition and validate the result."""
    models = available_model_ids()
    prompt = pipeline_generation_prompt(description, models)

    try:
        raw = provider.generate(prompt, planner_model)
    except llm_exceptions.LLMError as cause:
        raise as_domain_error(cause) from cause

    return parse_plan(raw, models)


def parse_plan(raw: str, available_models: list[str]) -> dict[str, Any]:
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

    fallback = default_model_id()
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise UpstreamResponseInvalid("The planner returned a malformed step.")
        step.setdefault("order", index)
        if step.get("model") not in available_models:
            step["model"] = fallback

    return plan


def ensure_runnable(pipeline: Pipeline) -> None:
    """Guard against running a pipeline that has no steps."""
    if not pipeline.steps.exists():
        raise ValidationFailed("This pipeline has no steps to run.")
