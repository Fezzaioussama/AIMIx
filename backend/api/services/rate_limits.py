"""Authentication rate-limit policy without retaining raw client addresses."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from api.exceptions import Throttled
from api.repositories.rate_limits import RateLimitAttempt, consume


@dataclass(frozen=True)
class RateLimitRequest:
    identity: str
    action: str
    limit: int
    window_seconds: int


def enforce(session: Session, secret_key: str, request: RateLimitRequest) -> None:
    digest = hmac.new(secret_key.encode(), request.identity.encode(), hashlib.sha256).hexdigest()
    attempt = RateLimitAttempt(digest, request.action, request.limit, request.window_seconds)
    retry_after = consume(session, attempt, datetime.now(timezone.utc))
    if retry_after is not None:
        raise Throttled("Too many authentication requests. Try again later.", retry_after)
