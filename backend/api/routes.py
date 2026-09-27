"""Routing table — no logic (AGENTS.md §2).

Auth-protected by default (§6): every router goes in PROTECTED_ROUTERS unless
it is deliberately public.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import current_user
from api.endpoints import auth, chat, models, pipelines

API_PREFIX = "/api"

PUBLIC_ROUTERS = (auth.public_router,)
PROTECTED_ROUTERS = (auth.router, chat.router, models.router, pipelines.router)


def api_router() -> APIRouter:
    router = APIRouter(prefix=API_PREFIX)
    for public in PUBLIC_ROUTERS:
        router.include_router(public)
    for protected in PROTECTED_ROUTERS:
        router.include_router(protected, dependencies=[Depends(current_user)])
    return router
