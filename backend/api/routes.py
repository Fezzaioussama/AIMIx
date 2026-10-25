"""Routing table — no logic (AGENTS.md §2).

Auth-protected by default (§6): every router goes in PROTECTED_ROUTERS unless
it is deliberately public.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import current_user
from api.endpoints import (
    agent_tools,
    auth,
    chat,
    documents,
    files,
    health,
    integrations,
    llm_settings,
    models,
    pipelines,
    runs,
    schedules,
    templates,
)

API_PREFIX = "/api"

PUBLIC_ROUTERS = (auth.public_router, health.router)
PROTECTED_ROUTERS = (
    auth.router,
    chat.router,
    models.router,
    pipelines.router,
    documents.router,
    agent_tools.router,
    llm_settings.router,
    templates.router,
    integrations.router,
    files.router,
    runs.router,
    schedules.router,
)


def api_router() -> APIRouter:
    router = APIRouter(prefix=API_PREFIX)
    for public in PUBLIC_ROUTERS:
        router.include_router(public)
    for protected in PROTECTED_ROUTERS:
        router.include_router(protected, dependencies=[Depends(current_user)])
    return router
