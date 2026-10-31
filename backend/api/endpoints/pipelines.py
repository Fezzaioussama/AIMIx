"""Pipeline endpoints. Each one validates input, calls a service or repository,
and shapes the result — no business logic lives here (AGENTS.md §2)."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Response

from api.deps import (
    CurrentUser,
    DbSession,
    PipelineRun,
    Profile,
    Providers,
    ToolCatalog,
    disk_room,
)
from api.models import Pipeline
from api.repositories import pipelines as repository
from api.schemas.pipelines import PipelineIn, PipelineOut, PipelinePatch, RunRequest, RunResponse
from api.schemas.planning import (
    ClarifyingQuestionOut,
    GenerateRequest,
    GenerateResponse,
    PipelineChangeOut,
    ReviseRequest,
    ReviseResponse,
)
from api.services import pipeline_flow
from api.services import pipeline_revision as revision_service
from api.services import pipelines as pipeline_service
from api.services.plan_questions import Answer, Clarification
from api.services.runs import RunStart
from api.throttling import user_rate_limit

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


def _changes(
    body: PipelineIn | PipelinePatch, current: Pipeline | None = None
) -> repository.PipelineChanges:
    """What the body saves, once its conditions and review loops are known to
    work in the pipeline it leaves (``current`` is what it replaces or patches)."""
    changes = repository.PipelineChanges(
        name=body.name,
        inputs=None if body.inputs is None else [field.model_dump() for field in body.inputs],
        steps=None if body.steps is None else [step.model_dump() for step in body.steps],
    )
    pipeline_flow.ensure_valid_flow(changes, current)
    return changes


@router.get("/")
def list_pipelines(user: CurrentUser, session: DbSession) -> list[PipelineOut]:
    return [PipelineOut.model_validate(p) for p in repository.for_user(session, user)]


#: Routes that save a pipeline: refused while the disk is nearly full (deps.disk_room).
SAVES = [Depends(disk_room)]


@router.post("/", status_code=201, dependencies=SAVES)
def create_pipeline(body: PipelineIn, user: CurrentUser, session: DbSession) -> PipelineOut:
    pipeline = repository.create_with_steps(session, user, _changes(body))
    return PipelineOut.model_validate(pipeline)


@router.post("/generate", dependencies=[Depends(user_rate_limit)])
def generate_pipeline(
    body: GenerateRequest, providers: Providers, profile: Profile, catalog: ToolCatalog
) -> GenerateResponse:
    answers = tuple(Answer(item.question, item.answer) for item in body.answers)
    clarification = Clarification(body.may_ask, answers)
    request = pipeline_service.PlanRequest(body.description, body.planner_model, clarification)
    plan = pipeline_service.generate(providers(), profile, request, catalog.available_sync())
    return GenerateResponse(
        generated_pipeline=plan.pipeline,
        questions=[ClarifyingQuestionOut.model_validate(asdict(q)) for q in plan.questions],
        available_models=profile.models,
    )


# Declared before the "/{pipeline_id}/" routes, like /generate, so no id route
# can ever claim the path.
@router.post("/revise", dependencies=[Depends(user_rate_limit)])
def revise_pipeline(
    body: ReviseRequest, providers: Providers, profile: Profile, catalog: ToolCatalog
) -> ReviseResponse:
    request = revision_service.RevisionRequest(
        body.pipeline.model_dump(), body.instruction, body.planner_model
    )
    revision = revision_service.revise(providers(), profile, request, catalog.available_sync())
    return ReviseResponse(
        revised_pipeline=revision.pipeline,
        changes=[PipelineChangeOut.model_validate(asdict(change)) for change in revision.changes],
        available_models=profile.models,
    )


@router.get("/{pipeline_id}/")
def get_pipeline(pipeline_id: int, user: CurrentUser, session: DbSession) -> PipelineOut:
    return PipelineOut.model_validate(repository.get_owned(session, user, pipeline_id))


@router.put("/{pipeline_id}/", dependencies=SAVES)
def replace_pipeline(
    pipeline_id: int, body: PipelineIn, user: CurrentUser, session: DbSession
) -> PipelineOut:
    pipeline = repository.get_owned(session, user, pipeline_id)
    updated = repository.replace_steps(session, pipeline, _changes(body, pipeline))
    return PipelineOut.model_validate(updated)


@router.patch("/{pipeline_id}/", dependencies=SAVES)
def update_pipeline(
    pipeline_id: int, body: PipelinePatch, user: CurrentUser, session: DbSession
) -> PipelineOut:
    pipeline = repository.get_owned(session, user, pipeline_id)
    updated = repository.replace_steps(session, pipeline, _changes(body, pipeline))
    return PipelineOut.model_validate(updated)


@router.delete("/{pipeline_id}/", status_code=204)
def delete_pipeline(pipeline_id: int, user: CurrentUser, session: DbSession) -> Response:
    repository.delete(session, repository.get_owned(session, user, pipeline_id))
    return Response(status_code=204)


@router.post("/{pipeline_id}/run", dependencies=[Depends(user_rate_limit)])
def run_pipeline(pipeline_id: int, body: RunRequest, context: PipelineRun) -> RunResponse:
    """Kept for API compatibility: a recorded run, waited for to its end, at most
    RUN_WAIT_MAX_SECONDS (then a 202 ``run_still_running``: the run goes on).
    New clients start one with ``POST /pipelines/{id}/runs`` and poll it."""
    pipeline = repository.get_owned(context.session, context.user, pipeline_id)
    start = RunStart(body.input, body.inputs, body.budget)
    result = context.runs.run_to_end(context.user, pipeline, start, context.agents())
    return RunResponse.model_validate(asdict(result))
