"""Settings → Memory: what the signed-in person told AIMIx to keep in mind for every
chat, plan and run. Each endpoint validates, calls the service and shapes the result."""

from __future__ import annotations

from fastapi import APIRouter

from api.deps import AppSettings, CurrentUser, DbSession
from api.schemas.memory import MemoryIn, MemoryOut
from api.services import user_memory as service

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("")
def read_memory(user: CurrentUser, session: DbSession, settings: AppSettings) -> MemoryOut:
    return MemoryOut.model_validate(service.read(session, user, settings.memory_max_chars))


@router.put("")
def save_memory(
    body: MemoryIn, user: CurrentUser, session: DbSession, settings: AppSettings
) -> MemoryOut:
    view = service.save(session, user, body.instructions, settings.memory_max_chars)
    return MemoryOut.model_validate(view)
