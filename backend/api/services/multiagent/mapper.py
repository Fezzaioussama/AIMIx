"""Inbound adapter: snapshot saved ORM records into graph contracts, and keep a
snapshot as JSON so a stored run can be executed again exactly as it started."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from api.models import Pipeline, PipelineStep
from api.services.multiagent.conditions import condition_from_data
from api.services.multiagent.contracts import InputField, PipelineSpec, StepSpec
from api.services.multiagent.reviews import review_from_data


def _step_spec(step: PipelineStep) -> StepSpec:
    selected = tuple(step.allowed_tools) if step.allowed_tools is not None else None
    return StepSpec(
        step.order,
        step.stage,
        step.title,
        step.prompt,
        step.model,
        step.role,
        selected,
        step.is_output,
        # Column defaults apply on insert, so an unsaved step may still hold None.
        step.expected_output or "",
        condition_from_data(step.condition),
        review_from_data(step.review),
    )


def _input_field(item: Mapping[str, str]) -> InputField:
    return InputField(item["name"], item.get("label", ""), item.get("description", ""))


def snapshot_pipeline(pipeline: Pipeline) -> PipelineSpec:
    """Copy loaded fields before the graph creates concurrent agent tasks."""
    return PipelineSpec(
        pipeline_id=pipeline.id,
        name=pipeline.name,
        steps=tuple(_step_spec(step) for step in pipeline.steps),
        inputs=tuple(_input_field(item) for item in pipeline.inputs or ()),
    )


def spec_to_json(spec: PipelineSpec) -> dict[str, Any]:
    """The definition a run stores: name, named inputs and steps, the same
    fields a saved pipeline has (``api/schemas/pipelines.PipelineIn``)."""
    return {
        "name": spec.name,
        "inputs": [asdict(field) for field in spec.inputs],
        "steps": [
            {
                **asdict(step),
                "allowed_tools": None if step.allowed_tools is None else list(step.allowed_tools),
            }
            for step in spec.steps
        ],
    }


def _stored_step(item: Mapping[str, Any]) -> StepSpec:
    selected = item.get("allowed_tools")
    return StepSpec(
        order=item["order"],
        stage=item["stage"],
        title=item.get("title", ""),
        prompt=item["prompt"],
        model=item["model"],
        role=item.get("role", ""),
        allowed_tools=None if selected is None else tuple(selected),
        is_output=bool(item.get("is_output", False)),
        expected_output=item.get("expected_output", ""),
        # Runs saved before conditions and review loops existed have neither key.
        condition=condition_from_data(item.get("condition")),
        review=review_from_data(item.get("review")),
    )


def spec_from_json(pipeline_id: int | None, definition: Mapping[str, Any]) -> PipelineSpec:
    """Rebuild the snapshot ``spec_to_json`` stored for a run."""
    return PipelineSpec(
        pipeline_id=pipeline_id,
        name=definition["name"],
        steps=tuple(_stored_step(item) for item in definition["steps"]),
        inputs=tuple(_input_field(item) for item in definition.get("inputs", ())),
    )
