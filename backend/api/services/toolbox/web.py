"""HTTP gateway for the web tools: Tavily search and guarded page fetches
(AGENTS.md §7 Adapter / Gateway over httpx).

Failures an agent can recover from raise ``ToolException``: the agent receives
them as an error result and can try another query or source, instead of the
whole pipeline run failing.

Page fetches go through ``api.services.web_download``, the core the pages users
read from a link share: public addresses only, every redirect hop checked, no
DNS-rebinding window, bodies decoded in bounded pieces (a compressed bomb stops
at WEB_FETCH_MAX_BYTES like any page) and WEB_FETCH_MAX_SECONDS for the whole
fetch, redirects included.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx
from langchain_core.tools import ToolException

from api.services.addresses import AddressNotAllowed, Resolver, resolve_host
from api.services.toolbox.config import ToolboxConfig
from api.services.toolbox.html_text import decode_page, html_to_text, page_charset, text_charset
from api.services.web_download import (
    USER_AGENT,
    Download,
    DownloadFailed,
    PageDownloader,
    UnwantedMediaType,
)

logger = logging.getLogger(__name__)

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
    """A fetched page's readable text."""

    url: str
    text: str = ""
    truncated: bool = False


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


def _page_text(page: Download) -> str:
    """The page as text, in the charset ``html_text``'s rules find (for HTML, the HTML
    standard's order), reduced to what a reader sees."""
    if "html" not in page.media_type:
        return decode_page(page.body, text_charset(page.body, page.charset)).strip()
    return html_to_text(decode_page(page.body, page_charset(page.body, page.charset)))


class WebGateway:
    """Search and fetch with the configured timeout and size limits.

    ``transport`` replaces the network in tests; fetches still read their
    bodies through ``BoundedBodies``.
    """

    def __init__(
        self,
        config: ToolboxConfig,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Resolver = resolve_host,
    ) -> None:
        self._config = config
        self._transport = transport
        self._pages = PageDownloader(
            config.timeout_seconds, config.fetch_max_seconds, transport, resolver
        )

    def _search_client(self) -> httpx.AsyncClient:
        # TAVILY_SEARCH_URL is the operator's: it keeps httpx's defaults, proxies included.
        return httpx.AsyncClient(
            transport=self._transport,
            timeout=self._config.timeout_seconds,
            headers={"User-Agent": USER_AGENT},
        )

    async def search(self, query: str) -> list[SearchHit]:
        payload = {
            "query": query,
            "max_results": self._config.search_max_results,
            "search_depth": "basic",
        }
        headers = {"Authorization": f"Bearer {self._config.search_api_key}"}
        try:
            async with self._search_client() as client:
                response = await client.post(self._config.search_url, json=payload, headers=headers)
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as cause:
            raise _failure("web_search", "Web search failed", cause) from cause
        return _search_hits(body)

    async def fetch(self, url: str) -> FetchedPage:
        """The readable text of the page at ``url``, within WEB_FETCH_MAX_SECONDS."""
        page = await self._download(url)
        text = _page_text(page)
        limit = self._config.fetch_max_chars
        return FetchedPage(page.url, text[:limit], page.truncated or len(text) > limit)

    async def _download(self, url: str) -> Download:
        limit = self._config.fetch_max_seconds
        try:
            return await self._pages.download(url, self._config.fetch_max_bytes, _is_text)
        except UnwantedMediaType as cause:
            raise ToolException(f"The page is {cause.media_type}, not text.") from cause
        except (DownloadFailed, AddressNotAllowed) as cause:
            raise ToolException(str(cause)) from cause
        except TimeoutError as cause:
            logger.warning("agent.tool_failed tool=fetch_url error=deadline")
            raise ToolException(f"Fetching the page took longer than {limit:g} seconds.") from cause
        except (httpx.HTTPError, httpx.InvalidURL) as cause:
            raise _failure("fetch_url", "Fetching the page failed", cause) from cause
