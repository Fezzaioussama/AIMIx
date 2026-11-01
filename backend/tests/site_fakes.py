"""Fake web sites for the page import tests (POST /api/documents/import-url):
what a site answers, what DNS says, and how a test sends a link. Nothing here
opens a real connection.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import page_downloader
from api.services.addresses import Resolver
from api.services.outbound import OutboundPolicy, guarded_transport
from api.services.web_download import PageDownloader
from tests.conftest import TEST_SETTINGS
from tests.network_fakes import FakeNetwork

PUBLIC_ADDRESS = "93.184.215.14"
#: Longer than DOCUMENT_URL_MIN_TEXT_CHARS, so a page holding it is no JavaScript shell.
ARTICLE = (
    "Retrieval-augmented generation lets a language model answer from documents it is "
    "given when a question is asked, rather than only from what it learned in training, "
    "which keeps its answers current and lets them name their sources."
)

Handler = Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]]


def resolver(table: dict[str, list[str]]) -> Resolver:
    async def resolve(host: str) -> list[str]:
        return table.get(host, [PUBLIC_ADDRESS])

    return resolve


def use_site(
    app: FastAPI, handler: Handler, hosts: dict[str, list[str]] | None = None, deadline: float = 5.0
) -> None:
    """Every page the app downloads comes from ``handler``; DNS answers from ``hosts``."""
    downloader = PageDownloader(
        TEST_SETTINGS.web_timeout_seconds,
        deadline,
        httpx.MockTransport(handler),
        resolver(hosts or {}),
    )
    app.dependency_overrides[page_downloader] = lambda: downloader


def use_network(app: FastAPI, network: FakeNetwork, lookups: Resolver) -> None:
    """Downloads go through the real guarded transport, over a fake socket layer."""
    transport = guarded_transport(OutboundPolicy(lookups), network)
    downloader = PageDownloader(TEST_SETTINGS.web_timeout_seconds, 5.0, transport, lookups)
    app.dependency_overrides[page_downloader] = lambda: downloader


def serving(body: bytes | str, content_type: str) -> Handler:
    content = body.encode() if isinstance(body, str) else body
    headers = {"content-type": content_type} if content_type else {}
    return lambda request: httpx.Response(200, content=content, headers=headers)


def recording(requests: list[httpx.Request]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=ARTICLE)

    return handler


def read_link(client: TestClient, url: str) -> httpx.Response:
    return client.post("/api/documents/import-url", json={"url": url})


def refused(response: httpx.Response, status: int, error: str, detail: str) -> None:
    assert response.status_code == status
    assert response.json() == {"error": error, "detail": detail}
