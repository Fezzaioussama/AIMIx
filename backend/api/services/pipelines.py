"""Pipeline orchestration: run a saved pipeline, and plan a new one with an LLM.

Takes and returns plain Python values — no web-framework request or response
objects (AGENTS.md §2).
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from functools import partial
from itertools import groupby
from operator import attrgetter
from time import perf_counter
from typing import Any, Protocol

from api.exceptions import UpstreamResponseInvalid, ValidationFailed
from api.models import STEP_ROLE_MAX_LENGTH, STEP_TITLE_MAX_LENGTH, Pipeline, PipelineStep
from api.services.agent_types import AgentOutcome, AgentTask, ToolCallTrace, ToolDescriptor
from api.services.catalog import available_model_ids, default_model_id
from api.services.errors import as_domain_error
from api.services.prompts import merge_stage_outputs, pipeline_generation_prompt, step_prompt
from config.settings import get_settings
from llm import exceptions as llm_exceptions
from llm.base import LLMProvider

logger = logging.getLogger(__name__)

JSON_OBJECT_PATTERN = re.compile(r"\{[\s\S]*\}")


@dataclass(frozen=True)
class StepResult:
    """One executed step (§7 DTO)."""

    step_order: int
    stage: int
    title: str
    model: str
    input_used: str
    output: str
    is_output: bool = False
    tool_calls: list[ToolCallTrace] = field(default_factory=list)


@dataclass(frozen=True)
class RunResult:
    pipeline_name: str
    final_output: str
    intermediate_results: list[StepResult]


class StepGenerator(Protocol):
    """Execute one configured agent task and report its tool activity."""

    def execute(self, task: AgentTask) -> AgentOutcome: ...


def run(pipeline: Pipeline, generator: StepGenerator, initial_input: str) -> RunResult:
    """Execute the stages in order (§7 Pipeline).

    Steps within a stage run in parallel on the same input; the stage's merged
    output becomes the next stage's input. Every step's result is returned,
    with the pipeline's outputs flagged.
    """
    current = initial_input
    results: list[StepResult] = []
    steps = list(pipeline.steps)
    stages = group_by_stage(steps)
    outputs = output_orders(steps)
    started = perf_counter()

    for steps in stages:
        stage_results = _run_stage(steps, generator, current)
        results.extend(stage_results)
        current = merge_stage_outputs(
            [(result.step_order, result.output) for result in stage_results]
        )

    logger.info(
        "pipeline.run pipeline_id=%s stages=%s steps=%s duration_ms=%.0f",
        pipeline.id,
        len(stages),
        len(results),
        (perf_counter() - started) * 1000,
    )
    return RunResult(
        pipeline_name=pipeline.name,
        final_output=current,
        intermediate_results=[
            replace(result, is_output=result.step_order in outputs) for result in results
        ],
    )


def output_orders(steps: list[PipelineStep]) -> set[int]:
    """The steps whose results are the pipeline's outputs.

    Marked steps when there are any; otherwise the last stage, which is what a
    pipeline produced before steps could be marked.
    """
    marked = {step.order for step in steps if step.is_output}
    if marked:
        return marked
    last_stage = max((step.stage for step in steps), default=0)
    return {step.order for step in steps if step.stage == last_stage}


def group_by_stage(steps: list[PipelineStep]) -> list[list[PipelineStep]]:
    """Stages in ascending order, each holding its steps sorted by ``order``."""
    ordered = sorted(steps, key=attrgetter("stage", "order"))
    return [list(group) for _, group in groupby(ordered, key=attrgetter("stage"))]


def _run_stage(
    steps: list[PipelineStep], generator: StepGenerator, stage_input: str
) -> list[StepResult]:
    """Run one stage's steps concurrently; results keep the steps' order.

    Agent calls are I/O-bound and each carries its own timeout, so a small
    thread pool is enough. The first failure is re-raised and queued steps are
    cancelled rather than spending further agent calls.
    """
    run_step = partial(_run_step, generator=generator, stage_input=stage_input)
    if len(steps) == 1:
        return [run_step(steps[0])]

    pool = ThreadPoolExecutor(
        max_workers=min(len(steps), get_settings().pipeline_max_parallel_steps)
    )
    try:
        return list(pool.map(run_step, steps))
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


def _run_step(step: PipelineStep, generator: StepGenerator, stage_input: str) -> StepResult:
    task = AgentTask(
        prompt=step_prompt(step.prompt, stage_input),
        model=step.model,
        role=step.role,
        allowed_tools=step.allowed_tools,
    )
    try:
        outcome = generator.execute(task)
    except llm_exceptions.LLMError as cause:
        raise as_domain_error(cause) from cause
    return StepResult(
        step_order=step.order,
        stage=step.stage,
        title=step.title,
        model=step.model,
        input_used=stage_input,
        output=outcome.output,
        tool_calls=outcome.tool_calls,
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
