"""Revise a pipeline draft from one sentence: the planner returns the whole revised
pipeline, which is sanitised like a generated plan and compared with the draft.

Nothing is saved: the user reviews the revision and saves it through the normal
pipeline endpoints. Plain Python values in and out (AGENTS.md §2).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from api.models import PIPELINE_NAME_MAX_LENGTH
from api.services.agent_types import ToolDescriptor
from api.services.llm import LLMProfile
from api.services.pipeline_changes import PipelineChange, diff_pipelines
from api.services.pipelines import PlannerCall, ask_planner
from api.services.prompts import pipeline_revision_prompt
from llm.base import LLMProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RevisionRequest:
    """What to change. ``pipeline`` is the current draft as plain data, the
    pipeline contract's fields; it may be unsaved. No ``planner_model`` means
    the profile's default model."""

    pipeline: Mapping[str, Any]
    instruction: str
    planner_model: str | None = None


@dataclass(frozen=True)
class Revision:
    """The revised pipeline, sanitised like a generated plan, and what changed."""

    pipeline: dict[str, Any]
    changes: list[PipelineChange]


def revise(
    provider: LLMProvider,
    profile: LLMProfile,
    request: RevisionRequest,
    tools: list[ToolDescriptor] | None = None,
) -> Revision:
    """Ask the planner to apply ``request.instruction`` to the draft; return the
    whole revised pipeline and its change list. Planner failures raise the same
    domain errors as generation (``ask_planner``)."""
    started = time.monotonic()
    prompt = pipeline_revision_prompt(request.pipeline, request.instruction, profile.models, tools)
    plan = ask_planner(provider, profile, PlannerCall(prompt, request.planner_model), tools)
    plan["name"] = _revised_name(plan.get("name"), request.pipeline.get("name"))
    changes = diff_pipelines(request.pipeline, plan)
    logger.info(
        "pipeline.revise steps=%d changes=%d duration_ms=%d",
        len(plan["steps"]),
        len(changes),
        (time.monotonic() - started) * 1000,
    )
    return Revision(plan, changes)


def _revised_name(proposed: object, current: object) -> str:
    """The planner's name, trimmed to the column's limit; the draft's name when
    the planner gave none."""
    if isinstance(proposed, str) and proposed.strip():
        return proposed.strip()[:PIPELINE_NAME_MAX_LENGTH]
    return current.strip() if isinstance(current, str) else ""
