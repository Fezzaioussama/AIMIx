"""Usage endpoint: what the signed-in user's runs used and cost lately, in all
and per pipeline. Validates the query, calls the usage service, shapes the
result (AGENTS.md §2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from api.deps import CurrentUser, DbSession
from api.schemas.usage import UsageQuery, UsageReportOut
from api.services.usage import usage_report

router = APIRouter(tags=["usage"])


@router.get("/usage")
def get_usage(
    user: CurrentUser, session: DbSession, query: Annotated[UsageQuery, Query()]
) -> UsageReportOut:
    return UsageReportOut.model_validate(usage_report(session, user, query.days))
