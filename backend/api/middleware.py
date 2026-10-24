"""Cross-cutting HTTP concerns: request size, allowed hosts, CORS and security headers."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.errors import error_body
from config.settings import Settings

BASE_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; "
        "object-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'"
    ),
}
HSTS_HEADER = {"Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload"}


class SecurityHeadersMiddleware:
    """Adds hardening headers to every HTTP response (pure ASGI, so streamed
    responses pass through untouched)."""

    def __init__(self, app: ASGIApp, headers: dict[str, str]) -> None:
        self.app = app
        self.headers = headers

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                for name, value in self.headers.items():
                    response_headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequestSizeLimitMiddleware:
    """Rejects a request whose declared Content-Length is over the limit before any
    of its body is read, so an oversized upload is never parsed or spooled to disk.
    A body sent without a Content-Length is still capped by the endpoint that reads it."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            declared = Headers(scope=scope).get("content-length", "")
            if declared.isdigit() and int(declared) > self.max_bytes:
                detail = f"The request is larger than the {self.max_bytes / 1_000_000:g} MB limit."
                response = JSONResponse(error_body("request_too_large", detail), status_code=413)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def install_middleware(app: FastAPI, settings: Settings) -> None:
    headers = dict(BASE_SECURITY_HEADERS)
    if settings.app_env == "production":
        headers.update(HSTS_HEADER)
    # Added first, so it sits innermost: its 413 still gets the security and CORS headers.
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(SecurityHeadersMiddleware, headers=headers)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["authorization", "content-type"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
