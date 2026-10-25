"""Run endpoints: start a pipeline run in the background, follow it, stop,
resume or delete it, and page through the history. Each one validates input,
calls the run service or repository, and shapes the result (AGENTS.md §2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from api.deps import CurrentUser, DbSession, PipelineRun, Runs, user_rate_limit
from api.repositories import pipelines as pipeline_repository
from api.repositories import runs as repository
from api.schemas.pipelines import RunRequest
from api.schemas.runs import ResumeRequest, RunListQuery, RunOut, RunPageOut, RunSummaryOut
from api.services.run_budget import NO_BUDGET
from api.services.runs import RunStart

router = APIRouter(tags=["runs"])


@router.post(
    "/pipelines/{pipeline_id}/runs", status_code=202, dependencies=[Depends(user_rate_limit)]
)
def start_run(pipeline_id: int, body: RunRequest, context: PipelineRun) -> RunOut:
    """Queue a run of a saved pipeline; poll ``GET /runs/{id}`` to follow it."""
    pipeline = pipeline_repository.get_owned(context.session, context.user, pipeline_id)
    started = context.runs.start(
        context.user, pipeline, RunStart(body.input, body.inputs, body.budget), context.agents()
    )
    return RunOut.model_validate(started.run)


@router.get("/runs")
def list_runs(
    user: CurrentUser, session: DbSession, query: Annotated[RunListQuery, Query()]
) -> RunPageOut:
    page = repository.page_for_user(
        session,
        user,
        repository.RunQuery(query.limit, query.offset, query.pipeline_id, query.status),
    )
    return RunPageOut(
        items=[RunSummaryOut.model_validate(run) for run in page.items], total=page.total
    )


@router.get("/runs/{run_id}")
def get_run(run_id: int, user: CurrentUser, session: DbSession) -> RunOut:
    return RunOut.model_validate(repository.get_owned(session, user, run_id))


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: int, user: CurrentUser, runs: Runs) -> RunOut:
    return RunOut.model_validate(runs.cancel(user, run_id))


@router.post("/runs/{run_id}/resume", dependencies=[Depends(user_rate_limit)])
def resume_run(run_id: int, context: PipelineRun, body: ResumeRequest | None = None) -> RunOut:
    """Continue a stopped run; an optional body sets new spending limits."""
    budget = body.budget if body is not None else NO_BUDGET
    return RunOut.model_validate(
        context.runs.resume(context.user, run_id, context.agents(), budget)
    )


@router.delete("/runs/{run_id}", status_code=204)
def delete_run(run_id: int, user: CurrentUser, runs: Runs) -> Response:
    runs.delete(user, run_id)
    return Response(status_code=204)
