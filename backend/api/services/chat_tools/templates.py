"""Chat tools that start a workflow from a ready-made one, as the Templates screen does:
the same catalogue and the same use case, so its steps get the person's default model
and only the tools they can use (AGENTS.md §3)."""

from __future__ import annotations

from typing import Any

from langchain.tools import tool
from langchain_core.tools import BaseTool

from api.exceptions import DomainError
from api.schemas.templates import TemplateUseIn
from api.services.chat_tools.common import refused, session_user
from api.services.chat_tools.scope import ChatScope
from api.services.chat_tools.workflows import team_of
from api.services.files.disk import disk_reserve
from api.services.templates import use as template_use
from api.services.templates.registry import all_templates
from config.settings import get_settings


def template_tools(scope: ChatScope) -> list[BaseTool]:
    """Bind the template tools to the signed-in person."""

    @tool
    def list_templates() -> list[dict[str, Any]]:
        """List the ready-made workflows the person can start from: each one's slug,
        title, category, what it does, how many agents it has and what it asks for."""
        return [
            {
                "slug": template.slug,
                "title": template.title,
                "category": template.category,
                "description": template.description,
                "agents": template.step_count,
                "inputs": [field.name for field in template.inputs],
            }
            for template in all_templates()
        ]

    @tool
    def use_template(slug: str, name: str | None = None) -> dict[str, Any]:
        """Create a workflow of your own from a ready-made one (see list_templates),
        named after it unless you give a name. Returns the saved team."""
        try:
            body = TemplateUseIn.model_validate({"name": name})
            choice = template_use.TemplateChoice(slug, body.name)
            catalog = scope.catalog(scope.database, scope.user)
            defaults = template_use.StepDefaults(scope.profile.models, catalog.available_sync)
            disk_reserve(get_settings()).ensure_room()
            with scope.database.session() as session:
                owner = session_user(session, scope.user)
                return team_of(template_use.use_template(session, owner, choice, defaults))
        except (ValueError, DomainError) as cause:
            raise refused(cause) from cause

    return [list_templates, use_template]
