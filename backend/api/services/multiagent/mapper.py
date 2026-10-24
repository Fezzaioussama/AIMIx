"""Inbound adapter: snapshot saved ORM records into graph contracts."""

from __future__ import annotations

from api.models import Pipeline, PipelineStep
from api.services.multiagent.contracts import InputField, PipelineSpec, StepSpec


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
    )


def _input_field(item: dict[str, str]) -> InputField:
    return InputField(item["name"], item.get("label", ""), item.get("description", ""))


def snapshot_pipeline(pipeline: Pipeline) -> PipelineSpec:
    """Copy loaded fields before the graph creates concurrent agent tasks."""
    return PipelineSpec(
        pipeline_id=pipeline.id,
        name=pipeline.name,
        steps=tuple(_step_spec(step) for step in pipeline.steps),
        inputs=tuple(_input_field(item) for item in pipeline.inputs or ()),
    )
