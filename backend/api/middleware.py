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
    # The microphone only for the app's own pages: Missions dictation (api/services/voice.py).
    "Permissions-Policy": "camera=(), microphone=(self), geolocation=()",
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
    """Caps every request body: a multipart upload at ``max_bytes``, any other body
    (JSON) at ``max_json_bytes``. A declared Content-Length over the cap is refused
    before any of the body is read; a body sent without one (chunked) is counted as
    it arrives and refused once it passes the cap. Either way nothing past the cap
    is read, parsed or spooled to disk, and this runs before routing, so before
    authentication."""

    def __init__(self, app: ASGIApp, max_bytes: int, max_json_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.max_json_bytes = max_json_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        multipart = headers.get("content-type", "").lower().startswith("multipart/")
        body = _CappedBody(
            scope, receive, send, self.max_bytes if multipart else self.max_json_bytes
        )
        declared = headers.get("content-length", "")
        if declared.isdigit() and int(declared) > body.limit:
            await body.refuse()
            return
        try:
            await self.app(scope, body.receive, body.send)
        except _BodyTooLarge:
            if not body.responded:
                await body.refuse()


class _BodyTooLarge(Exception):
    """Raised into the app from ``receive`` to stop it reading an oversized body."""


class _CappedBody:
    """One request's ``receive`` and ``send``, counting body bytes as they arrive.

    Past the cap, ``receive`` raises; whatever the app answers then (FastAPI turns a
    failed body read into a 400) is replaced by the 413."""

    def __init__(self, scope: Scope, receive: Receive, send: Send, limit: int) -> None:
        self.scope, self._receive, self._send, self.limit = scope, receive, send, limit
        self.received = 0
        self.overflowed = False
        self.responded = False

    async def receive(self) -> Message:
        message = await self._receive()
        if message["type"] == "http.request":
            self.received += len(message.get("body", b""))
            if self.received > self.limit:
                self.overflowed = True
                raise _BodyTooLarge
        return message

    async def send(self, message: Message) -> None:
        if not self.overflowed:
            self.responded = self.responded or message["type"] == "http.response.start"
            await self._send(message)
        elif message["type"] == "http.response.start" and not self.responded:
            await self.refuse()

    async def refuse(self) -> None:
        self.responded = True
        detail = f"The request is larger than the {self.limit / 1_000_000:g} MB limit."
        response = JSONResponse(error_body("request_too_large", detail), status_code=413)
        await response(self.scope, self._receive, self._send)


def install_middleware(app: FastAPI, settings: Settings) -> None:
    headers = dict(BASE_SECURITY_HEADERS)
    if settings.app_env == "production":
        headers.update(HSTS_HEADER)
    # Added first, so it sits innermost: its 413 still gets the security and CORS headers.
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_bytes=settings.max_request_bytes,
        max_json_bytes=settings.request_max_json_bytes,
    )
    app.add_middleware(SecurityHeadersMiddleware, headers=headers)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["authorization", "content-type"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
