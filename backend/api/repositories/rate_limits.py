"""Persistence for database-backed request throttling.

Every change to a counter is one conditional statement, so concurrent requests
(threads or app processes) never count past the limit between a read and a
write. Buckets whose window ended are deleted whenever a new one is created.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy import Update, and_, delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from api.models import RateLimitBucket


@dataclass(frozen=True)
class RateLimitAttempt:
    identity_hash: str
    action: str
    limit: int
    window_seconds: int


def consume(session: Session, attempt: RateLimitAttempt, now: datetime) -> int | None:
    """Count one request; return retry seconds when the window is exhausted."""
    try:
        return _consume(session, attempt, now)
    except IntegrityError:
        # Another request created this bucket first: count against theirs.
        session.rollback()
        return _consume(session, attempt, now)


def retry_after(session: Session, attempt: RateLimitAttempt, now: datetime) -> int | None:
    """Seconds until the window has room again, or None when it has room now.
    Counts nothing."""
    row = session.execute(
        select(RateLimitBucket.window_started_at, RateLimitBucket.hits).where(_key(attempt))
    ).one_or_none()
    if row is None or row.hits < attempt.limit:
        return None
    started = row.window_started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    remaining = attempt.window_seconds - (now - started).total_seconds()
    return max(1, int(remaining)) if remaining > 0 else None


def release(session: Session, attempt: RateLimitAttempt) -> None:
    """Give back one request ``consume`` counted (it was refused for another reason)."""
    session.execute(
        update(RateLimitBucket)
        .where(_key(attempt), RateLimitBucket.hits > 0)
        .values(hits=RateLimitBucket.hits - 1)
        .execution_options(synchronize_session=False)
    )
    session.commit()


def clear(session: Session, attempt: RateLimitAttempt) -> None:
    """Forget the bucket: the next request starts a new window."""
    session.execute(delete(RateLimitBucket).where(_key(attempt)))
    session.commit()


def _consume(session: Session, attempt: RateLimitAttempt, now: datetime) -> int | None:
    cutoff = now - timedelta(seconds=attempt.window_seconds)
    counted = _count_in_window(session, attempt, cutoff) or _restart_ended(
        session, attempt, now, cutoff
    )
    wait = None if counted else retry_after(session, attempt, now)
    if not counted and wait is None:
        _create(session, attempt, now, cutoff)
    session.commit()
    return wait


def _count_in_window(session: Session, attempt: RateLimitAttempt, cutoff: datetime) -> bool:
    """One more hit on a running window that still has room."""
    return _changed(
        session,
        update(RateLimitBucket)
        .where(
            _key(attempt),
            RateLimitBucket.window_started_at > cutoff,
            RateLimitBucket.hits < attempt.limit,
        )
        .values(hits=RateLimitBucket.hits + 1),
    )


def _restart_ended(
    session: Session, attempt: RateLimitAttempt, now: datetime, cutoff: datetime
) -> bool:
    """The first hit of a new window, on a bucket whose window has ended."""
    return _changed(
        session,
        update(RateLimitBucket)
        .where(_key(attempt), RateLimitBucket.window_started_at <= cutoff)
        .values(hits=1, window_started_at=now),
    )


def _create(session: Session, attempt: RateLimitAttempt, now: datetime, cutoff: datetime) -> None:
    """Start the bucket, pruning this action's buckets whose window has ended
    (an action always has the same window, so they would restart anyway)."""
    session.execute(
        delete(RateLimitBucket).where(
            RateLimitBucket.action == attempt.action, RateLimitBucket.window_started_at <= cutoff
        )
    )
    session.add(
        RateLimitBucket(
            identity_hash=attempt.identity_hash,
            action=attempt.action,
            window_started_at=now,
            hits=1,
        )
    )
    session.flush()


def _key(attempt: RateLimitAttempt) -> ColumnElement[bool]:
    return and_(
        RateLimitBucket.identity_hash == attempt.identity_hash,
        RateLimitBucket.action == attempt.action,
    )


def _changed(session: Session, statement: Update) -> bool:
    """Whether the statement changed the one bucket it targets."""
    result = cast(
        "CursorResult[Any]",
        session.execute(statement.execution_options(synchronize_session=False)),
    )
    return result.rowcount == 1
