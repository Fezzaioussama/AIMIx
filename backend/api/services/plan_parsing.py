"""Turning a planner's reply into a plan that can be stored (§5 S): decode its JSON, keep
only the inputs and step fields a save accepts, set aside flow that cannot work, and keep a
new team on one model. Kept apart from the planner call (``pipelines``), so it can be tested
without a provider."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any

from api.exceptions import UpstreamResponseInvalid
from api.models import (
    PIPELINE_INPUT_DESCRIPTION_MAX_LENGTH,
    PIPELINE_INPUT_LABEL_MAX_LENGTH,
    PIPELINE_MAX_INPUTS,
    STEP_EXPECTED_OUTPUT_MAX_LENGTH,
    STEP_ROLE_MAX_LENGTH,
    STEP_TITLE_MAX_LENGTH,
)
from api.services.multiagent.conditions import condition_from_data
from api.services.multiagent.reviews import review_from_data
from api.services.pipeline_flow import flow_problems, flow_step
from api.services.pipeline_inputs import INPUT_DEFAULT_MAX_LENGTH, input_name_error

JSON_OBJECT_PATTERN = re.compile(r"\{[\s\S]*\}")


def decoded(raw: str) -> object:
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
    plan = decoded(raw)
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
    that no earlier input took, at most ``PIPELINE_MAX_INPUTS`` of them, each with
    the value it suggests to the run form (``default_value``) when it fits.

    A name is checked, never shortened, because the prompts refer to it whole.
    """
    inputs: dict[str, dict[str, str]] = {}
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"))
        if input_name_error(name) or name in inputs:
            continue
        default = _text(item.get("default_value"))
        inputs[name] = {
            "name": name,
            "label": _text(item.get("label"), PIPELINE_INPUT_LABEL_MAX_LENGTH),
            "description": _text(item.get("description"), PIPELINE_INPUT_DESCRIPTION_MAX_LENGTH),
            # A value too long to keep is left out rather than cut: half of pasted notes
            # would mislead more than an empty field.
            "default_value": default if len(default) <= INPUT_DEFAULT_MAX_LENGTH else "",
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


def on_default_model(steps: list[dict[str, Any]], default_model: str, asked: str) -> None:
    """Put every step on the default model, except one whose model the request names
    (``asked``, matched by the id's last part, e.g. "grok-4.20"): planners scatter the
    steps of a team over many models, which costs more and fails more, as one model
    replying with nothing or garbled text stops or spoils the whole run."""
    request = asked.lower()
    for step in steps:
        if step["model"].rsplit("/", 1)[-1].lower() not in request:
            step["model"] = default_model
