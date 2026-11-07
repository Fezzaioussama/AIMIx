"""Data access for what a run's owner thought of it (``services/run_feedback``): the
rating and note kept on the run, and the latest noted runs the planner learns from.
Apart from ``repositories/runs`` so that module does not grow (AGENTS.md §4)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, load_only

from api.models import Run, User


def save(session: Session, run: Run, rating: int | None, note: str) -> None:
    """Keep the owner's rating and note on the run (the caller checked it has ended)."""
    run.rating = rating
    run.feedback = note
    session.commit()


def latest_noted(session: Session, user: User, limit: int) -> list[Run]:
    """The user's newest runs with a note, newest first; only what a lesson needs is read."""
    rows = session.scalars(
        select(Run)
        .where(Run.user_id == user.id, Run.feedback != "")
        .options(load_only(Run.pipeline_name, Run.rating, Run.feedback))
        .order_by(Run.created_at.desc(), Run.id.desc())
        .limit(limit)
    )
    return list(rows)
