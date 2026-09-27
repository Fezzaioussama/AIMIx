"""Data access for pipelines (AGENTS.md §7 Repository).

Services and endpoints go through these helpers instead of writing queries
inline, so ownership filtering lives in exactly one place. Each write commits
its own transaction.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from api.exceptions import NotFound
from api.models import Pipeline, PipelineStep, User


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


def create_with_steps(
    session: Session, user: User, name: str, steps: Iterable[dict[str, Any]]
) -> Pipeline:
    pipeline = Pipeline(user=user, name=name, steps=_new_steps(steps))
    session.add(pipeline)
    session.commit()
    return pipeline


def replace_steps(
    session: Session,
    pipeline: Pipeline,
    name: str | None,
    steps: Iterable[dict[str, Any]] | None,
) -> Pipeline:
    """Rename and/or replace every step, in one transaction."""
    if name is not None:
        pipeline.name = name
    if steps is not None:
        pipeline.steps.clear()
        # Delete the old rows before inserting, or reused `order` values would
        # collide with the unique constraint inside the same flush.
        session.flush()
        pipeline.steps.extend(_new_steps(steps))
    session.commit()
    return pipeline


def delete(session: Session, pipeline: Pipeline) -> None:
    session.delete(pipeline)
    session.commit()
