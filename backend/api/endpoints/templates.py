"""Mission templates: the gallery, and starting a pipeline from one. Each
endpoint validates input, calls the service and shapes the result (AGENTS.md §2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import TemplateUse, user_rate_limit
from api.schemas.pipelines import PipelineOut
from api.schemas.templates import TemplateOut, TemplateUseIn
from api.services.templates import registry
from api.services.templates.use import TemplateChoice, use_template

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("")
def list_templates() -> list[TemplateOut]:
    return [
        TemplateOut.model_validate(template, from_attributes=True)
        for template in registry.all_templates()
    ]


@router.post("/{slug}/use", status_code=201, dependencies=[Depends(user_rate_limit)])
def create_from_template(
    slug: str, context: TemplateUse, body: TemplateUseIn | None = None
) -> PipelineOut:
    choice = TemplateChoice(slug, body.name if body else None)
    pipeline = use_template(context.session, context.user, choice, context.defaults)
    return PipelineOut.model_validate(pipeline)
