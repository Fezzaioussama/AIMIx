"""Rate-limit policy (per client for auth, per account for costly actions and
failed sign-ins) without retaining raw client addresses or usernames."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from api.exceptions import Throttled
from api.repositories import rate_limits as repository
from api.repositories.rate_limits import RateLimitAttempt


@dataclass(frozen=True)
class RateLimitRequest:
    identity: str
    action: str
    limit: int
    window_seconds: int
    #: What the refused caller reads.
    message: str = "Too many authentication requests. Try again later."


def enforce(session: Session, secret_key: str, request: RateLimitRequest) -> None:
    """Count the request, or raise Throttled when its window is exhausted."""
    retry_after = repository.consume(session, _attempt(secret_key, request), _now())
    if retry_after is not None:
        raise Throttled(request.message, retry_after)


def ensure_room(session: Session, secret_key: str, request: RateLimitRequest) -> None:
    """Raise Throttled when the window is exhausted, without counting anything."""
    retry_after = repository.retry_after(session, _attempt(secret_key, request), _now())
    if retry_after is not None:
        raise Throttled(request.message, retry_after)


def count(session: Session, secret_key: str, request: RateLimitRequest) -> None:
    """Count one event (a failed sign-in) that ``ensure_room`` checks later."""
    repository.consume(session, _attempt(secret_key, request), _now())


def release(session: Session, secret_key: str, request: RateLimitRequest) -> None:
    """Give back one request ``enforce`` counted."""
    repository.release(session, _attempt(secret_key, request))


def reset(session: Session, secret_key: str, request: RateLimitRequest) -> None:
    repository.clear(session, _attempt(secret_key, request))


def client_address(forwarded_for: Sequence[str], peer: str, trusted_hops: int) -> str:
    """The client's address, given every X-Forwarded-For header value, the socket
    peer, and how many proxies in front of the app append to that header.

    No trusted proxy, or no header: the peer. A client can prepend entries but
    never remove the ones the proxies append, so the entry ``trusted_hops`` from
    the right is the address the outermost trusted proxy saw. A chain shorter
    than that was written by the trusted proxies alone: its leftmost entry."""
    entries = [item.strip() for value in forwarded_for for item in value.split(",")]
    entries = [entry for entry in entries if entry]
    if trusted_hops == 0 or not entries:
        return peer
    return _host(entries[-trusted_hops] if len(entries) >= trusted_hops else entries[0])


def _host(entry: str) -> str:
    """The address without a port a proxy may append (``1.2.3.4:5678``,
    ``[2001:db8::1]:5678``), so one client's connections share a counter."""
    if entry.startswith("[") and "]" in entry:
        return entry[1 : entry.index("]")]
    return entry.split(":", 1)[0] if entry.count(":") == 1 else entry


def _attempt(secret_key: str, request: RateLimitRequest) -> RateLimitAttempt:
    digest = hmac.new(secret_key.encode(), request.identity.encode(), hashlib.sha256).hexdigest()
    return RateLimitAttempt(digest, request.action, request.limit, request.window_seconds)


def _now() -> datetime:
    return datetime.now(timezone.utc)
