"""Usage endpoint: what the signed-in user's runs, chats and planning used and cost
lately, in all and per pipeline, and today's spending against the daily allowance
of the server's key. Validates the query, calls the usage service, shapes the result
(AGENTS.md §2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from api.account_deps import UsageView
from api.schemas.usage import UsageQuery, UsageReportOut
from api.services.usage import UsageAsk, usage_report

router = APIRouter(tags=["usage"])


@router.get("/usage")
def get_usage(view: UsageView, query: Annotated[UsageQuery, Query()]) -> UsageReportOut:
    report = usage_report(view.session, view.user, UsageAsk(query.days, view.allowance))
    return UsageReportOut.model_validate(report)
