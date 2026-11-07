"""Signing a user's MCP server requests with its OAuth access token: an ``httpx.Auth``
the adapter's connection carries, renewed through the same guarded client when the
token has expired and kept through ``keep`` so the next connection starts fresh."""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator, Callable, Generator

import httpx
from anyio import to_thread

from api.services.integrations.oauth_tokens import Tokens, refresh_request, renewed_tokens

Keep = Callable[[Tokens], None]


class OAuthBearer(httpx.Auth):
    """``Authorization: Bearer <access token>`` on every request, renewed first when
    the token has expired and a refresh token is at hand."""

    requires_response_body = True

    def __init__(self, tokens: Tokens, keep: Keep | None = None) -> None:
        self._tokens = tokens
        self._keep = keep

    @property
    def tokens(self) -> Tokens:
        return self._tokens

    def sync_auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response]:
        # The MCP client is async; a sync caller gets the token as it stands.
        request.headers["Authorization"] = f"Bearer {self._tokens.access_token}"
        yield request

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        if self._tokens.expired(time.time()) and self._tokens.refresh_token:
            response = yield refresh_request(self._tokens)
            await response.aread()
            renewed = renewed_tokens(self._tokens, response)
            if renewed is not None:
                self._tokens = renewed
                if self._keep is not None:
                    await to_thread.run_sync(self._keep, renewed)
        request.headers["Authorization"] = f"Bearer {self._tokens.access_token}"
        yield request
