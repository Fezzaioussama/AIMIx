"""Per-account caps checked inside the write they bound (AGENTS.md §6).

Counting first and writing afterwards lets two requests pass the check
together. Here the write comes first: the owner's row is locked (on a database
that locks rows; SQLite lets one writer at a time anyway), the write is
flushed, and the count in that same transaction sees it and every row
committed before it. Past the cap, the transaction is rolled back and the
caller's refusal raised, so nothing of the write is kept.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from api.exceptions import DomainError
from api.models import User


@dataclass(frozen=True)
class Quota:
    """At most ``cap`` rows of one kind per account; past it, ``refusal`` is raised."""

    cap: int
    refusal: DomainError


def lock_owner(session: Session, user_id: int) -> None:
    """Before a capped write: make another capped write of the same account wait
    for this transaction (``SELECT ... FOR UPDATE``; SQLite has no such lock)."""
    session.execute(select(User.id).where(User.id == user_id).with_for_update())


def enforce(session: Session, count: Select[Any], quota: Quota) -> None:
    """After the write, before its commit: roll the transaction back and raise
    the quota's refusal when ``count`` (which sees the write) is past the cap."""
    session.flush()
    if (session.scalar(count) or 0) > quota.cap:
        session.rollback()
        raise quota.refusal
