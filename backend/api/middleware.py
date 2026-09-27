"""Cross-cutting HTTP concerns: allowed hosts, CORS and security headers."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from config.settings import Settings

BASE_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
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


def install_middleware(app: FastAPI, settings: Settings) -> None:
    headers = dict(BASE_SECURITY_HEADERS)
    if settings.app_env == "production":
        headers.update(HSTS_HEADER)
    app.add_middleware(SecurityHeadersMiddleware, headers=headers)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["authorization", "content-type"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
