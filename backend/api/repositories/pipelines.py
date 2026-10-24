"""Data access for pipelines (AGENTS.md §7 Repository).

Services and endpoints go through these helpers instead of writing queries
inline, so ownership filtering lives in exactly one place. Each write commits
its own transaction.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from api.exceptions import NotFound
from api.models import Pipeline, PipelineStep, User


@dataclass(frozen=True)
class PipelineChanges:
    """What a write sets. On an update, ``None`` keeps the stored value."""

    name: str | None = None
    inputs: list[dict[str, str]] | None = None
    steps: list[dict[str, Any]] | None = None


def _owned_by(user: User) -> Select[tuple[Pipeline]]:
    return select(Pipeline).where(Pipeline.user_id == user.id).options(selectinload(Pipeline.steps))


def for_user(session: Session, user: User) -> list[Pipeline]:
    """The user's pipelines, newest first."""
    query = _owned_by(user).order_by(Pipeline.created_at.desc(), Pipeline.id.desc())
    return list(session.scalars(query))


def get_owned(session: Session, user: User, pipeline_id: int) -> Pipeline:
    """Fetch a pipeline the user owns, or raise NotFound.

    Ownership is part of the lookup rather than a separate check, so a pipeline
    belonging to someone else is indistinguishable from one that is absent.
    """
    pipeline = session.scalar(_owned_by(user).where(Pipeline.id == pipeline_id))
    if pipeline is None:
        raise NotFound(f"Pipeline {pipeline_id} was not found.")
    return pipeline


def _new_steps(steps: Iterable[dict[str, Any]]) -> list[PipelineStep]:
    """Rows in execution order, as a fresh load would return them."""
    rows = [PipelineStep(**step) for step in steps]
    return sorted(rows, key=lambda step: (step.stage, step.order))


def create_with_steps(session: Session, user: User, changes: PipelineChanges) -> Pipeline:
    """A new pipeline for ``user``; whatever ``changes`` leaves out starts empty."""
    pipeline = Pipeline(user=user, name="", inputs=[])
    session.add(pipeline)
    return replace_steps(session, pipeline, changes)


def replace_steps(session: Session, pipeline: Pipeline, changes: PipelineChanges) -> Pipeline:
    """Rename, redeclare the inputs and/or replace every step, in one transaction."""
    if changes.name is not None:
        pipeline.name = changes.name
    if changes.inputs is not None:
        pipeline.inputs = changes.inputs
    if changes.steps is not None:
        if pipeline.steps:
            pipeline.steps.clear()
            # Delete the old rows before inserting, or reused `order` values would
            # collide with the unique constraint inside the same flush.
            session.flush()
        pipeline.steps.extend(_new_steps(changes.steps))
    session.commit()
    return pipeline


def delete(session: Session, pipeline: Pipeline) -> None:
    session.delete(pipeline)
    session.commit()
