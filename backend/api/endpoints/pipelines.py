"""Pipeline endpoints. Each one validates input, calls a service or repository,
and shapes the result — no business logic lives here (AGENTS.md §2)."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Response

from api.deps import CurrentUser, DbSession, PipelineRun, Profile, Providers, ToolCatalog
from api.repositories import pipelines as repository
from api.schemas.pipelines import (
    GenerateRequest,
    GenerateResponse,
    PipelineIn,
    PipelineOut,
    PipelinePatch,
    RunRequest,
    RunResponse,
)
from api.services import pipelines as pipeline_service

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


def _changes(body: PipelineIn | PipelinePatch) -> repository.PipelineChanges:
    return repository.PipelineChanges(
        name=body.name,
        inputs=None if body.inputs is None else [field.model_dump() for field in body.inputs],
        steps=None if body.steps is None else [step.model_dump() for step in body.steps],
    )


@router.get("/")
def list_pipelines(user: CurrentUser, session: DbSession) -> list[PipelineOut]:
    return [PipelineOut.model_validate(p) for p in repository.for_user(session, user)]


@router.post("/", status_code=201)
def create_pipeline(body: PipelineIn, user: CurrentUser, session: DbSession) -> PipelineOut:
    pipeline = repository.create_with_steps(session, user, _changes(body))
    return PipelineOut.model_validate(pipeline)


@router.post("/generate")
def generate_pipeline(
    body: GenerateRequest, providers: Providers, profile: Profile, catalog: ToolCatalog
) -> GenerateResponse:
    request = pipeline_service.PlanRequest(body.description, body.planner_model)
    plan = pipeline_service.generate(providers(), profile, request, catalog.available_sync())
    return GenerateResponse(generated_pipeline=plan, available_models=profile.models)


@router.get("/{pipeline_id}/")
def get_pipeline(pipeline_id: int, user: CurrentUser, session: DbSession) -> PipelineOut:
    return PipelineOut.model_validate(repository.get_owned(session, user, pipeline_id))


@router.put("/{pipeline_id}/")
def replace_pipeline(
    pipeline_id: int, body: PipelineIn, user: CurrentUser, session: DbSession
) -> PipelineOut:
    pipeline = repository.get_owned(session, user, pipeline_id)
    updated = repository.replace_steps(session, pipeline, _changes(body))
    return PipelineOut.model_validate(updated)


@router.patch("/{pipeline_id}/")
def update_pipeline(
    pipeline_id: int, body: PipelinePatch, user: CurrentUser, session: DbSession
) -> PipelineOut:
    pipeline = repository.get_owned(session, user, pipeline_id)
    updated = repository.replace_steps(session, pipeline, _changes(body))
    return PipelineOut.model_validate(updated)


@router.delete("/{pipeline_id}/", status_code=204)
def delete_pipeline(pipeline_id: int, user: CurrentUser, session: DbSession) -> Response:
    repository.delete(session, repository.get_owned(session, user, pipeline_id))
    return Response(status_code=204)


@router.post("/{pipeline_id}/run")
def run_pipeline(pipeline_id: int, body: RunRequest, context: PipelineRun) -> RunResponse:
    pipeline = repository.get_owned(context.session, context.user, pipeline_id)
    pipeline_service.ensure_runnable(pipeline)
    result = pipeline_service.run(pipeline, context.agents(), body.input, body.inputs)
    return RunResponse.model_validate(asdict(result))
