"""The signed-in user's scheduled runs: list, create, change (including on and
off), delete, run now, and preview a timing. Each endpoint validates, calls the
service and shapes the result (AGENTS.md §2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from api.deps import Now, PipelineRun, Schedules
from api.schemas.runs import RunOut
from api.schemas.schedules import (
    ScheduleIn,
    ScheduleListQuery,
    ScheduleOut,
    SchedulePatch,
    SchedulePreviewOut,
    ScheduleTimingIn,
)
from api.services.schedules import requests, service
from api.throttling import user_rate_limit

router = APIRouter(prefix="/schedules", tags=["schedules"])


@router.get("")
def list_schedules(
    access: Schedules, query: Annotated[ScheduleListQuery, Query()]
) -> list[ScheduleOut]:
    views = service.list_views(access, query.pipeline_id)
    return [ScheduleOut.model_validate(view) for view in views]


@router.post("", status_code=201)
def create_schedule(body: ScheduleIn, access: Schedules) -> ScheduleOut:
    return ScheduleOut.model_validate(service.create(access, requests.draft_of(body)))


# Declared before the "/{schedule_id}" routes, so no id route can claim the path.
@router.post("/preview")
def preview_schedule(body: ScheduleTimingIn, now: Now) -> SchedulePreviewOut:
    return SchedulePreviewOut(next_run_at=service.preview(requests.timing_of(body), now))


@router.patch("/{schedule_id}")
def update_schedule(schedule_id: int, body: SchedulePatch, access: Schedules) -> ScheduleOut:
    return ScheduleOut.model_validate(service.update(access, schedule_id, requests.edit_of(body)))


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int, access: Schedules) -> Response:
    service.delete(access, schedule_id)
    return Response(status_code=204)


@router.post("/{schedule_id}/run", status_code=202, dependencies=[Depends(user_rate_limit)])
def run_schedule_now(schedule_id: int, access: Schedules, context: PipelineRun) -> RunOut:
    """Start one of the schedule's runs now; poll ``GET /runs/{id}`` to follow it."""
    run = service.run_now(access, schedule_id, context.runs, context.agents())
    return RunOut.model_validate(run)
