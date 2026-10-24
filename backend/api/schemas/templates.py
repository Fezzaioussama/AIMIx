"""Contracts for the mission template gallery."""

from __future__ import annotations

from pydantic import BaseModel

from api.schemas.pipelines import PipelineInputField, PipelineName


class TemplateOut(BaseModel):
    """One template as the gallery shows it. Its steps stay on the server until
    the template is used; the counts tell the user how big the team is."""

    slug: str
    title: str
    category: str
    description: str
    #: What the user fills in on every run of the pipeline.
    inputs: list[PipelineInputField]
    step_count: int
    stage_count: int


class TemplateUseIn(BaseModel):
    """Body of POST /templates/<slug>/use, which may be left out."""

    #: Omitted names the pipeline after the template.
    name: PipelineName | None = None
