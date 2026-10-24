"""Start a pipeline from a template: the use case behind POST /templates/<slug>/use.

The template's steps go through the planner's own sanitiser
(``pipelines.sanitise_step``), so every step gets the owner's default model and
keeps only the tools the owner can use, by the same rule as a generated plan.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.orm import Session

from api.models import Pipeline, User
from api.repositories import pipelines as repository
from api.services.agent_types import ToolDescriptor
from api.services.pipelines import sanitise_step
from api.services.templates.contracts import MissionTemplate
from api.services.templates.registry import get_template

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TemplateChoice:
    slug: str
    #: None names the pipeline after the template.
    name: str | None = None


@dataclass(frozen=True)
class StepDefaults:
    """What each step of a new pipeline takes from its owner's account."""

    #: The owner's model catalogue, their default model first.
    models: list[str]
    #: Discovers the tools the owner's agents can use. Called only once the
    #: template is found, so an unknown slug costs no discovery.
    tools: Callable[[], list[ToolDescriptor]]


def template_steps(
    template: MissionTemplate, models: list[str], tools: list[str]
) -> list[dict[str, Any]]:
    """The template's steps, ready to store: numbered in order, each on the
    first of ``models`` (templates name none), with only the named tools that
    are in ``tools``."""
    steps = [step.as_plan() for step in template.steps]
    for index, step in enumerate(steps, start=1):
        sanitise_step(step, index, models, tools)
    return steps


def use_template(
    session: Session, user: User, choice: TemplateChoice, defaults: StepDefaults
) -> Pipeline:
    """Create the user's own pipeline from a template, or raise NotFound."""
    template = get_template(choice.slug)
    available = [tool.name for tool in defaults.tools()]
    changes = repository.PipelineChanges(
        name=choice.name or template.title,
        inputs=[asdict(field) for field in template.inputs],
        steps=template_steps(template, defaults.models, available),
    )
    pipeline = repository.create_with_steps(session, user, changes)
    logger.info(
        "templates.used slug=%s pipeline_id=%s user_id=%s steps=%d",
        template.slug,
        pipeline.id,
        user.id,
        len(pipeline.steps),
    )
    return pipeline
