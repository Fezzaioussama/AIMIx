"""FastAPI dependencies that throttle requests: the client's address, the auth
rate limit and the registration limit (per client) and the costly-route rate
limit (per account), each counter persisted so every app process shares it
(api.services.rate_limits); and the one account copy built at a time."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from api.deps import AppSettings, CurrentUser, DbSession
from api.exceptions import DomainError, ExportsBusy
from api.services.rate_limits import RateLimitRequest, client_address, enforce, release


def request_client(request: Request, settings: AppSettings) -> str:
    """The client's address (TRUSTED_PROXY_HOPS says which proxy headers to trust)."""
    peer = request.client.host if request.client else "unknown"
    forwarded = request.headers.getlist("x-forwarded-for")
    return client_address(forwarded, peer, settings.trusted_proxy_hops)


ClientAddress = Annotated[str, Depends(request_client)]


def auth_rate_limit(
    request: Request, client: ClientAddress, session: DbSession, settings: AppSettings
) -> None:
    """Persist one counter per client and auth path, shared by every app process."""
    enforce(
        session,
        settings.secret_key,
        RateLimitRequest(
            client,
            request.url.path,
            settings.auth_rate_limit_requests,
            settings.auth_rate_limit_window_seconds,
        ),
    )


def registration_rate_limit(
    client: ClientAddress, session: DbSession, settings: AppSettings
) -> Iterator[None]:
    """Accounts one client may create per window, whatever the auth limit allows.
    Each attempt takes its place atomically before the account is made, so
    sign-ups sent at once cannot all pass; a refused one (a taken name, a weak
    password) raises out of the ``yield`` and gives its place back."""
    created = RateLimitRequest(
        client,
        "registration",
        settings.registration_rate_limit_requests,
        settings.registration_rate_limit_window_seconds,
        "Too many accounts were created from this address. Try again later.",
    )
    enforce(session, settings.secret_key, created)
    try:
        yield
    except DomainError:
        release(session, settings.secret_key, created)
        raise


#: One account copy built at a time in this process: each holds a whole account in
#: memory (up to ACCOUNT_EXPORT_MAX_CHARS), so copies made at once must not add up.
_EXPORTING = threading.Lock()


def one_export_at_a_time() -> Iterator[None]:
    """Hold the process's one export slot for the whole request, building the JSON
    included; another request meanwhile is refused (503), never queued."""
    if not _EXPORTING.acquire(blocking=False):
        raise ExportsBusy("Another copy of an account is being prepared. Try again in a minute.")
    try:
        yield
    finally:
        _EXPORTING.release()


def user_rate_limit(
    request: Request, user: CurrentUser, session: DbSession, settings: AppSettings
) -> None:
    """One counter per account and route (its path template, so ids in the URL
    share it), for routes that make the server spend: add it to a route's
    ``dependencies``."""
    route = request.scope.get("route")
    enforce(
        session,
        settings.secret_key,
        RateLimitRequest(
            f"user:{user.id}",
            getattr(route, "path", request.url.path),
            settings.user_rate_limit_requests,
            settings.user_rate_limit_window_seconds,
            "Too many requests. Try again later.",
        ),
    )
