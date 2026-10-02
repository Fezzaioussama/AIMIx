"""Pipeline endpoints. Each one validates input, calls a service or repository,
and shapes the result — no business logic lives here (AGENTS.md §2)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Response

from api.deps import CurrentUser, DbSession, PipelineRun, Providers, ToolCatalog
from api.repositories import pipelines as repository
from api.schemas.pipelines import (
    GenerateRequest,
    GenerateResponse,
    PipelineIn,
    PipelineOut,
    PipelinePatch,
    PipelineStepIn,
    RunRequest,
    RunResponse,
)
from api.services import pipelines as pipeline_service
from api.services.catalog import available_model_ids

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


def _rows(steps: list[PipelineStepIn] | None) -> list[dict[str, Any]] | None:
    return None if steps is None else [step.model_dump() for step in steps]


@router.get("/")
def list_pipelines(user: CurrentUser, session: DbSession) -> list[PipelineOut]:
    return [PipelineOut.model_validate(p) for p in repository.for_user(session, user)]


@router.post("/", status_code=201)
def create_pipeline(body: PipelineIn, user: CurrentUser, session: DbSession) -> PipelineOut:
    pipeline = repository.create_with_steps(session, user, body.name, _rows(body.steps) or [])
    return PipelineOut.model_validate(pipeline)


@router.post("/generate")
def generate_pipeline(
    body: GenerateRequest, providers: Providers, catalog: ToolCatalog
) -> GenerateResponse:
    tools = catalog.available_sync()
    plan = pipeline_service.generate(providers(), body.description, body.planner_model or "", tools)
    return GenerateResponse(generated_pipeline=plan, available_models=available_model_ids())


@router.get("/{pipeline_id}/")
def get_pipeline(pipeline_id: int, user: CurrentUser, session: DbSession) -> PipelineOut:
    return PipelineOut.model_validate(repository.get_owned(session, user, pipeline_id))


@router.put("/{pipeline_id}/")
def replace_pipeline(
    pipeline_id: int, body: PipelineIn, user: CurrentUser, session: DbSession
) -> PipelineOut:
    pipeline = repository.get_owned(session, user, pipeline_id)
    updated = repository.replace_steps(session, pipeline, body.name, _rows(body.steps))
    return PipelineOut.model_validate(updated)


@router.patch("/{pipeline_id}/")
def update_pipeline(
    pipeline_id: int, body: PipelinePatch, user: CurrentUser, session: DbSession
) -> PipelineOut:
    pipeline = repository.get_owned(session, user, pipeline_id)
    updated = repository.replace_steps(session, pipeline, body.name, _rows(body.steps))
    return PipelineOut.model_validate(updated)


@router.delete("/{pipeline_id}/", status_code=204)
def delete_pipeline(pipeline_id: int, user: CurrentUser, session: DbSession) -> Response:
    repository.delete(session, repository.get_owned(session, user, pipeline_id))
    return Response(status_code=204)


@router.post("/{pipeline_id}/run")
def run_pipeline(pipeline_id: int, body: RunRequest, context: PipelineRun) -> RunResponse:
    pipeline = repository.get_owned(context.session, context.user, pipeline_id)
    pipeline_service.ensure_runnable(pipeline)
    result = pipeline_service.run(pipeline, context.agents(), body.input)
    return RunResponse.model_validate(asdict(result))
