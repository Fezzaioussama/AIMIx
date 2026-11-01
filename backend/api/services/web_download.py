"""Download a page from a URL that a user or a model chose, from public addresses
only (AGENTS.md §6; §7 Gateway over httpx). One core for the fetch_url tool and
for the pages users read into a run (documents/web_import.py), §3.

Every hop of a redirect chain is refused up front when its host does not resolve
or resolves to any loopback, private, link-local or otherwise non-global address
(``api.services.addresses``), and the connection itself is made by
``api.services.outbound``, which checks the addresses it resolves and connects to
exactly those: neither a model nor a DNS server that changes its answer can steer
a download into the server's own network (SSRF, DNS rebinding). Private addresses
are refused whatever INTEGRATIONS_ALLOW_PRIVATE_NETWORK says. Bodies arrive
decoded in bounded pieces, so a compressed bomb stops at the byte cap like any
page; each request has its own timeout, and the whole download, redirects
included, a deadline.

Every hop, the first included, must be an absolute http(s) URL without a user name
or password, whose host httpx can encode. Failures stay neutral, for each caller to
put in its own words: ``UnusableUrl``,
``AddressNotAllowed`` and its ``HostNotFound``, ``TooManyRedirects``,
``UnwantedMediaType``, ``TimeoutError`` at the deadline, and httpx's own errors.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import anyio
import httpx

from api.services.addresses import Resolver, public_addresses, resolve_host
from api.services.outbound import BoundedBodies, OutboundPolicy, guarded_client, guarded_transport

MAX_REDIRECTS = 5
USER_AGENT = "AIMIx-agent/1.0"


class DownloadFailed(Exception):
    """The page cannot be downloaded, for a reason the network itself does not raise."""


class UnusableUrl(DownloadFailed):
    """Not an absolute http(s) URL, or one that cannot be parsed."""


class TooManyRedirects(DownloadFailed):
    """The page redirected more than MAX_REDIRECTS times."""


class UnwantedMediaType(DownloadFailed):
    """The page is of a type the caller does not take; its body was never read."""

    def __init__(self, media_type: str) -> None:
        super().__init__(media_type)
        self.media_type = media_type


@dataclass(frozen=True)
class Download:
    """A page as downloaded: where it ended up after redirects, and what it holds."""

    url: str
    #: Lower-case and without parameters, e.g. "text/html"; "" when the site names none.
    media_type: str
    #: The charset the Content-Type header names, else None.
    charset: str | None
    body: bytes
    #: True when the body went on past the byte cap and was cut there.
    truncated: bool


def _host(url: str) -> str:
    """The host of an absolute http(s) URL with no user name or password in it, else
    ``UnusableUrl``. Every hop is held to this, so a redirect cannot add credentials:
    httpx would send them as Basic auth, and they would name the document."""
    try:
        parts = urlsplit(url)
        host, _port = parts.hostname, parts.port  # .port raises on a bad one
    except ValueError as cause:  # e.g. "http://[abc/"
        raise UnusableUrl("That is not a valid URL.") from cause
    if parts.scheme not in ("http", "https") or not host:
        raise UnusableUrl("Only absolute http or https URLs can be fetched.")
    if parts.username is not None:
        raise UnusableUrl("A URL with a user name or password is never fetched.")
    return host


def _next_hop(url: str, location: str) -> str:
    try:
        return urljoin(url, location)
    except ValueError as cause:
        raise UnusableUrl("The page redirected to an invalid URL.") from cause


async def _read_capped(response: httpx.Response, limit: int) -> tuple[bytes, bool]:
    body = bytearray()
    async for chunk in response.aiter_bytes():
        body.extend(chunk)
        if len(body) > limit:
            return bytes(body[:limit]), True
    return bytes(body), False


async def _read(
    response: httpx.Response, url: str, max_bytes: int, accept: Callable[[str], bool]
) -> Download:
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    media_type = content_type.split(";", 1)[0].strip().lower()
    if not accept(media_type):
        raise UnwantedMediaType(media_type)
    body, truncated = await _read_capped(response, max_bytes)
    return Download(url, media_type, response.charset_encoding, body, truncated)


async def _get(
    client: httpx.AsyncClient, url: str, max_bytes: int, accept: Callable[[str], bool]
) -> Download | str:
    """The page at ``url``, or the URL it redirects to. httpx reads a host by IDNA
    2008, which refuses some names DNS accepts (``xn--n3h.net``), this hop's or the one
    its redirect names: that is ``UnusableUrl``, not a crash."""
    try:
        async with client.stream("GET", url) as response:
            if response.is_redirect:
                return _next_hop(url, response.headers["location"])
            return await _read(response, url, max_bytes, accept)
    except UnicodeError as cause:  # what idna raises
        raise UnusableUrl("That web address cannot be opened.") from cause


class PageDownloader:
    """GET pages with ``timeout_seconds`` per request and ``deadline_seconds`` for
    a whole download. ``transport`` replaces the network in tests; bodies are
    still read through ``BoundedBodies``."""

    def __init__(
        self,
        timeout_seconds: float,
        deadline_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Resolver = resolve_host,
    ) -> None:
        self._timeout = timeout_seconds
        self._deadline = deadline_seconds
        self._transport = transport
        self._resolver = resolver

    def _client(self) -> httpx.AsyncClient:
        transport = (
            BoundedBodies(self._transport)
            if self._transport is not None
            else guarded_transport(OutboundPolicy(self._resolver))
        )
        return guarded_client(
            transport,
            timeout=self._timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=False,
        )

    async def download(self, url: str, max_bytes: int, accept: Callable[[str], bool]) -> Download:
        """The page at ``url``, after up to MAX_REDIRECTS redirects, cut at
        ``max_bytes``. ``accept`` says by media type whether its body is wanted at
        all; ``TimeoutError`` once the deadline passes."""
        with anyio.fail_after(self._deadline):
            async with self._client() as client:
                return await self._follow(client, url, max_bytes, accept)

    async def _follow(
        self, client: httpx.AsyncClient, url: str, max_bytes: int, accept: Callable[[str], bool]
    ) -> Download:
        for _ in range(MAX_REDIRECTS + 1):
            await public_addresses(_host(url), self._resolver)
            hop = await _get(client, url, max_bytes, accept)
            if isinstance(hop, Download):
                return hop
            url = hop
        raise TooManyRedirects(f"The page redirected more than {MAX_REDIRECTS} times.")
