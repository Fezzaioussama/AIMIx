"""Model catalogue endpoint — lets the client stay free of a hard-coded list."""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas.pipelines import ModelsResponse
from api.services.catalog import available_model_ids, default_model_id

router = APIRouter(tags=["models"])


@router.get("/models")
def list_models() -> ModelsResponse:
    return ModelsResponse(models=available_model_ids(), default=default_model_id())
