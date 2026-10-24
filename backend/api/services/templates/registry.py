"""The template catalogue: slug -> template (AGENTS.md §7 Registry).

Adding a template is a new entry in one of the theme modules, never a new
branch. The order here is the gallery's order.
"""

from __future__ import annotations

from api.exceptions import NotFound
from api.services.templates import data, documents, launch, marketing, research
from api.services.templates.contracts import MissionTemplate

CATALOGUE: tuple[MissionTemplate, ...] = (
    *research.TEMPLATES,
    *documents.TEMPLATES,
    *data.TEMPLATES,
    *marketing.TEMPLATES,
    *launch.TEMPLATES,
)

TEMPLATES: dict[str, MissionTemplate] = {template.slug: template for template in CATALOGUE}


def all_templates() -> list[MissionTemplate]:
    """Every template, in gallery order."""
    return list(TEMPLATES.values())


def get_template(slug: str) -> MissionTemplate:
    """The template with this slug, or NotFound."""
    template = TEMPLATES.get(slug)
    if template is None:
        raise NotFound(f"Template '{slug}' was not found.")
    return template
