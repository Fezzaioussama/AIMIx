"""Model catalogue endpoint — lets the client stay free of a hard-coded list."""

from __future__ import annotations

from fastapi import APIRouter

from api.deps import Profile
from api.schemas.pipelines import ModelsResponse

router = APIRouter(tags=["models"])


@router.get("/models")
def list_models(profile: Profile) -> ModelsResponse:
    """The signed-in user's provider catalogue and default (Settings page)."""
    return ModelsResponse(models=profile.models, default=profile.default_model)
