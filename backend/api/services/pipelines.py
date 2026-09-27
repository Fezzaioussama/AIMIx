"""Pipeline orchestration: run a saved pipeline, and plan a new one with an LLM.

Takes and returns plain Python values — no Django request or response objects
(AGENTS.md §2).
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from itertools import groupby
from operator import attrgetter
from time import perf_counter
from typing import Any

from django.conf import settings

from api.exceptions import UpstreamResponseInvalid, ValidationFailed
from api.models import Pipeline, PipelineStep
from api.services.catalog import available_model_ids, default_model_id
from api.services.errors import as_domain_error
from api.services.prompts import merge_stage_outputs, pipeline_generation_prompt, step_prompt
from llm import exceptions as llm_exceptions
from llm.base import LLMProvider

logger = logging.getLogger(__name__)

JSON_OBJECT_PATTERN = re.compile(r"\{[\s\S]*\}")


@dataclass(frozen=True)
class StepResult:
    """One executed step (§7 DTO)."""

    step_order: int
    stage: int
    model: str
    input_used: str
    output: str


@dataclass(frozen=True)
class RunResult:
    pipeline_name: str
    final_output: str
    intermediate_results: list[StepResult]


def run(pipeline: Pipeline, provider: LLMProvider, initial_input: str) -> RunResult:
    """Execute the stages in order (§7 Pipeline).

    Steps within a stage run in parallel on the same input; the stage's merged
    output becomes the next stage's input. Every step's result is returned.
    """
    current = initial_input
    results: list[StepResult] = []
    stages = group_by_stage(list(pipeline.steps.all()))
    started = perf_counter()

    for steps in stages:
        stage_results = _run_stage(steps, provider, current)
        results.extend(stage_results)
        current = merge_stage_outputs(
            [(result.step_order, result.output) for result in stage_results]
        )

    logger.info(
        "pipeline.run pipeline_id=%s stages=%s steps=%s duration_ms=%.0f",
        pipeline.pk,
        len(stages),
        len(results),
        (perf_counter() - started) * 1000,
    )
    return RunResult(
        pipeline_name=pipeline.name, final_output=current, intermediate_results=results
    )


def group_by_stage(steps: list[PipelineStep]) -> list[list[PipelineStep]]:
    """Stages in ascending order, each holding its steps sorted by ``order``."""
    ordered = sorted(steps, key=attrgetter("stage", "order"))
    return [list(group) for _, group in groupby(ordered, key=attrgetter("stage"))]


def _run_stage(
    steps: list[PipelineStep], provider: LLMProvider, stage_input: str
) -> list[StepResult]:
    """Run one stage's steps concurrently; results keep the steps' order.

    Provider calls are I/O-bound and each carries its own timeout, so a small
    thread pool is enough. The first failure is re-raised and queued steps are
    cancelled rather than spending further provider calls.
    """
    run_step = partial(_run_step, provider=provider, stage_input=stage_input)
    if len(steps) == 1:
        return [run_step(steps[0])]

    pool = ThreadPoolExecutor(max_workers=min(len(steps), settings.PIPELINE_MAX_PARALLEL_STEPS))
    try:
        return list(pool.map(run_step, steps))
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


def _run_step(step: PipelineStep, provider: LLMProvider, stage_input: str) -> StepResult:
    try:
        output = provider.generate(step_prompt(step.prompt, stage_input), step.model)
    except llm_exceptions.LLMError as cause:
        raise as_domain_error(cause) from cause
    return StepResult(
        step_order=step.order,
        stage=step.stage,
        model=step.model,
        input_used=stage_input,
        output=output,
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
        _sanitise_step(step, index, available_models, fallback)

    return plan


def _sanitise_step(
    step: dict[str, Any], index: int, available_models: list[str], fallback_model: str
) -> None:
    """Make a planner step storable: unique order, a valid stage, a known model.

    ``order`` is renumbered by position because planners that group steps into
    parallel stages tend to repeat it; a missing or invalid stage falls back to
    the step's own position, i.e. sequential.
    """
    step["order"] = index
    stage = step.get("stage")
    if isinstance(stage, bool) or not isinstance(stage, int) or stage < 1:
        step["stage"] = index
    if step.get("model") not in available_models:
        step["model"] = fallback_model


def ensure_runnable(pipeline: Pipeline) -> None:
    """Guard against running a pipeline that has no steps."""
    if not pipeline.steps.exists():
        raise ValidationFailed("This pipeline has no steps to run.")
