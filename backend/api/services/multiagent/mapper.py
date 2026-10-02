"""Inbound adapter: snapshot saved ORM records into graph contracts."""

from __future__ import annotations

from api.models import Pipeline, PipelineStep
from api.services.multiagent.contracts import PipelineSpec, StepSpec


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
    )


def snapshot_pipeline(pipeline: Pipeline) -> PipelineSpec:
    """Copy loaded fields before the graph creates concurrent agent tasks."""
    return PipelineSpec(
        pipeline_id=pipeline.id,
        name=pipeline.name,
        steps=tuple(_step_spec(step) for step in pipeline.steps),
    )
