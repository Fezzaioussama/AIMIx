"""Persistence for database-backed request throttling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models import RateLimitBucket


@dataclass(frozen=True)
class RateLimitAttempt:
    identity_hash: str
    action: str
    limit: int
    window_seconds: int


def consume(session: Session, attempt: RateLimitAttempt, now: datetime) -> int | None:
    """Consume one request; return retry seconds when the window is exhausted."""
    query = select(RateLimitBucket).where(
        RateLimitBucket.identity_hash == attempt.identity_hash,
        RateLimitBucket.action == attempt.action,
    )
    bucket = session.scalar(query)
    if bucket is None:
        bucket = RateLimitBucket(identity_hash=attempt.identity_hash, action=attempt.action, hits=1)
        session.add(bucket)
    else:
        current = now if bucket.window_started_at.tzinfo else now.replace(tzinfo=None)
        retry_after = _consume_existing(bucket, attempt, current)
        if retry_after is not None:
            return retry_after
    session.commit()
    return None


def _consume_existing(
    bucket: RateLimitBucket, attempt: RateLimitAttempt, now: datetime
) -> int | None:
    if now >= bucket.window_started_at + timedelta(seconds=attempt.window_seconds):
        bucket.window_started_at = now
        bucket.hits = 1
    elif bucket.hits >= attempt.limit:
        elapsed = (now - bucket.window_started_at).total_seconds()
        return max(1, int(attempt.window_seconds - elapsed))
    else:
        bucket.hits += 1
    return None
