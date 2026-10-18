"""Liveness probe for the hosting platform's health check (Railway)."""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas.health import HealthResponse

#: Public on purpose: the platform probes it without credentials, and it
#: reveals nothing but that the process is serving requests (§6).
router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> HealthResponse:
    return HealthResponse(status="ok")
