"""Data access for each person's standing instructions (AGENTS.md §7 Repository):
one row per account, read by owner only. Each write commits its own transaction."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models import User, UserMemory


def get(session: Session, user: User) -> UserMemory | None:
    return session.scalar(select(UserMemory).where(UserMemory.user_id == user.id))


def instructions_of(session: Session, user: User) -> str:
    """What the person told AIMIx to keep in mind; "" until they save something."""
    row = get(session, user)
    return row.instructions if row is not None else ""


def save(session: Session, user: User, instructions: str, now: datetime) -> UserMemory:
    """Write the instructions, making the account's row the first time."""
    row = get(session, user)
    if row is None:
        row = UserMemory(user_id=user.id)
        session.add(row)
    row.instructions = instructions
    row.updated_at = now
    session.commit()
    session.refresh(row)
    return row
