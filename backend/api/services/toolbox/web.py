"""HTTP gateway for the web tools: Tavily search and guarded page fetches
(AGENTS.md §7 Adapter / Gateway over httpx).

Failures an agent can recover from raise ``ToolException``: the agent receives
them as an error result and can try another query or source, instead of the
whole pipeline run failing.

Page fetches only reach public addresses. Every hop of a redirect chain is
resolved and refused when any address is loopback, private, link-local or
otherwise non-global (``api.services.addresses``), so a model cannot be
steered into the server's own network (SSRF). httpx resolves the host again
when it connects; operators who cannot accept that DNS-rebinding window can
drop ``fetch_url`` from AGENT_BUILTIN_TOOLS.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from langchain_core.tools import ToolException

from api.services.addresses import AddressNotAllowed, Resolver, ensure_public_host, resolve_host
from api.services.toolbox.config import ToolboxConfig
from api.services.toolbox.html_text import html_to_text

logger = logging.getLogger(__name__)

MAX_REDIRECTS = 5
USER_AGENT = "AIMIx-agent/1.0"
TEXT_MEDIA_TYPES = frozenset(
    {"application/json", "application/xml", "application/xhtml+xml", "application/javascript"}
)


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class FetchedPage:
    """One fetched hop: either readable text or where the server redirected."""

    url: str
    text: str = ""
    truncated: bool = False
    redirect: str | None = None


def _media_type(content_type: str) -> str:
    return content_type.split(";", 1)[0].strip().lower()


def _is_text(media_type: str) -> bool:
    # A missing Content-Type is common on plain pages; decode it and let the agent judge.
    return (
        not media_type
        or media_type.startswith("text/")
        or media_type in TEXT_MEDIA_TYPES
        or media_type.endswith(("+json", "+xml"))
    )


def _reason(cause: Exception) -> str:
    if isinstance(cause, httpx.HTTPStatusError):
        return f"HTTP {cause.response.status_code}"
    if isinstance(cause, httpx.TimeoutException):
        return "timed out"
    return type(cause).__name__


def _failure(tool: str, message: str, cause: Exception) -> ToolException:
    # Queries and URLs may carry user data, so only the failure kind is logged (§6).
    logger.warning("agent.tool_failed tool=%s error=%s", tool, _reason(cause))
    return ToolException(f"{message}: {_reason(cause)}.")


def _search_hits(body: Any) -> list[SearchHit]:
    results = body.get("results") if isinstance(body, dict) else None
    if not isinstance(results, list):
        raise ToolException("Web search returned an unexpected response.")
    return [
        SearchHit(
            str(item.get("title") or ""), str(item.get("url") or ""), str(item.get("content") or "")
        )
        for item in results
        if isinstance(item, dict)
    ]


async def _read_capped(response: httpx.Response, limit: int) -> tuple[bytes, bool]:
    body = bytearray()
    async for chunk in response.aiter_bytes():
        body.extend(chunk)
        if len(body) > limit:
            return bytes(body[:limit]), True
    return bytes(body), False


class WebGateway:
    """Search and fetch with the configured timeout and size limits."""

    def __init__(
        self,
        config: ToolboxConfig,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Resolver = resolve_host,
    ) -> None:
        self._config = config
        self._transport = transport
        self._resolver = resolver

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=self._transport,
            timeout=self._config.timeout_seconds,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=False,
        )

    async def search(self, query: str) -> list[SearchHit]:
        payload = {
            "query": query,
            "max_results": self._config.search_max_results,
            "search_depth": "basic",
        }
        headers = {"Authorization": f"Bearer {self._config.search_api_key}"}
        try:
            async with self._client() as client:
                response = await client.post(self._config.search_url, json=payload, headers=headers)
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as cause:
            raise _failure("web_search", "Web search failed", cause) from cause
        return _search_hits(body)

    async def fetch(self, url: str) -> FetchedPage:
        """Follow up to MAX_REDIRECTS redirects, checking every hop is public."""
        async with self._client() as client:
            for _ in range(MAX_REDIRECTS + 1):
                await self._ensure_public(url)
                page = await self._get(client, url)
                if page.redirect is None:
                    return page
                url = page.redirect
        raise ToolException(f"The page redirected more than {MAX_REDIRECTS} times.")

    async def _ensure_public(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ToolException("Only absolute http or https URLs can be fetched.")
        try:
            await ensure_public_host(parts.hostname, self._resolver)
        except AddressNotAllowed as cause:
            raise ToolException(str(cause)) from cause

    async def _get(self, client: httpx.AsyncClient, url: str) -> FetchedPage:
        try:
            async with client.stream("GET", url) as response:
                if response.is_redirect:
                    return FetchedPage(url, redirect=urljoin(url, response.headers["location"]))
                response.raise_for_status()
                media_type = _media_type(response.headers.get("content-type", ""))
                if not _is_text(media_type):
                    raise ToolException(f"The page is {media_type}, not text.")
                body, truncated = await _read_capped(response, self._config.fetch_max_bytes)
                raw = body.decode(response.encoding or "utf-8", errors="replace")
        except (httpx.HTTPError, httpx.InvalidURL) as cause:
            raise _failure("fetch_url", "Fetching the page failed", cause) from cause
        text = html_to_text(raw) if "html" in media_type else raw.strip()
        limit = self._config.fetch_max_chars
        return FetchedPage(url, text[:limit], truncated or len(text) > limit)
