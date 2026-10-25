"""FastAPI dependencies that throttle requests: the client's address, the auth
rate limit (per client) and the costly-route rate limit (per account). Each
counter is persisted, so every app process shares it (api.services.rate_limits)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from api.deps import AppSettings, CurrentUser, DbSession
from api.services.rate_limits import RateLimitRequest, client_address, enforce


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
