"""Sharing a run's report: its owner makes, reads and withdraws the link (protected),
and anyone who has the link reads the report (public, read-only). Each endpoint
validates, calls the service and shapes the result (AGENTS.md §2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from api.deps import DbSession
from api.schemas.runs import RunOut, RunShareOut, shared_view
from api.services import run_sharing
from api.share_deps import Shares
from api.throttling import shared_run_rate_limit

router = APIRouter(tags=["runs"])
public_router = APIRouter(tags=["runs"])


@router.get("/runs/{run_id}/share")
def get_share(run_id: int, access: Shares) -> RunShareOut | None:
    """The run's link, or null while it is not shared."""
    link = run_sharing.link_of(access, run_id)
    return None if link is None else RunShareOut.model_validate(link)


@router.post("/runs/{run_id}/share")
def share_run(run_id: int, access: Shares) -> RunShareOut:
    """Make the link (once the run has ended); the same link comes back after that."""
    return RunShareOut.model_validate(run_sharing.share(access, run_id))


@router.delete("/runs/{run_id}/share", status_code=204)
def unshare_run(run_id: int, access: Shares) -> Response:
    run_sharing.unshare(access, run_id)
    return Response(status_code=204)


@public_router.get("/shared/{token}", dependencies=[Depends(shared_run_rate_limit)])
def read_shared_run(token: str, session: DbSession) -> RunOut:
    """The report a link shows: the run without what it was given, its prompts, the
    requests that waited for its owner, or what the owner thought of it. Public: the
    token in the path is the credential."""
    return shared_view(RunOut.model_validate(run_sharing.shared_run(session, token)))
