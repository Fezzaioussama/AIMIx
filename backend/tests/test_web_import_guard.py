"""The page import's guard (POST /api/documents/import-url): sites that do not hand
the page over, only public web addresses (SSRF, DNS rebinding), and the HTTP contract.

Sites are httpx.MockTransport handlers and DNS is a fake resolver; the guarded
transport runs over tests/network_fakes.py. Nothing leaves the process.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from time import perf_counter

import anyio
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import app_settings
from api.exceptions import DocumentReadersBusy
from api.services.documents.contracts import SlotPool
from api.services.documents.gate import extraction_slot
from api.services.documents.web_import import (
    PUBLIC_ONLY,
    REFUSED,
    TOO_SLOW,
    UNREACHABLE,
    LinkLimits,
    PageImporter,
)
from api.services.web_download import MAX_REDIRECTS, PageDownloader
from config.settings import Settings
from tests.conftest import TEST_SETTINGS
from tests.network_fakes import FakeNetwork, changing
from tests.site_fakes import (
    ARTICLE,
    PUBLIC_ADDRESS,
    read_link,
    recording,
    refused,
    resolver,
    serving,
    use_network,
    use_site,
)
from tests.test_documents import LIMITS

# --- sites that do not answer with the page -------------------------------------------


@pytest.mark.parametrize("status", [401, 403, 429])
def test_a_site_that_turns_readers_away_suggests_saving_a_pdf(
    app: FastAPI, auth_client: TestClient, status: int
) -> None:
    use_site(app, lambda request: httpx.Response(status, text="Just a moment..."))

    refused(read_link(auth_client, "https://medium.test/"), 502, "page_unreachable", REFUSED)


@pytest.mark.parametrize("status", [404, 500])
def test_another_error_answer_names_the_status(
    app: FastAPI, auth_client: TestClient, status: int
) -> None:
    use_site(app, lambda request: httpx.Response(status, text="Not here"))

    detail = f"AIMIx couldn't open this page (the site answered {status})."
    refused(read_link(auth_client, "https://site.test/gone"), 502, "page_unreachable", detail)


def test_a_site_that_cannot_be_reached(app: FastAPI, auth_client: TestClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    use_site(app, handler)

    refused(read_link(auth_client, "https://down.test/"), 502, "page_unreachable", UNREACHABLE)


def test_a_host_that_does_not_exist_is_unreachable_not_private(
    app: FastAPI, auth_client: TestClient
) -> None:
    use_site(app, serving(ARTICLE, "text/plain"), {"wikipedia.og": []})

    response = read_link(auth_client, "https://wikipedia.og/wiki/RAG")

    refused(response, 502, "page_unreachable", UNREACHABLE)


def test_a_slow_answer(app: FastAPI, auth_client: TestClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    use_site(app, handler)

    refused(read_link(auth_client, "https://slow.test/"), 502, "page_unreachable", TOO_SLOW)


def test_the_whole_download_has_a_deadline(app: FastAPI, auth_client: TestClient) -> None:
    async def drip(request: httpx.Request) -> httpx.Response:
        await anyio.sleep(0.3)  # each hop well within WEB_TIMEOUT_SECONDS
        return httpx.Response(302, headers={"location": "/next"})

    use_site(app, drip, deadline=0.2)
    started = perf_counter()

    response = read_link(auth_client, "https://drip.test/")

    refused(response, 502, "page_unreachable", TOO_SLOW)
    assert perf_counter() - started < 2


def test_more_redirects_than_the_limit(app: FastAPI, auth_client: TestClient) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(302, headers={"location": "/again"})

    use_site(app, handler)

    refused(read_link(auth_client, "https://loop.test/"), 502, "page_unreachable", UNREACHABLE)
    assert len(requests) == MAX_REDIRECTS + 1


# --- only public web pages ---------------------------------------------------------


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1", "64:ff9b::7f00:1", "fe80::1%2"]
)
def test_a_host_on_a_private_address_is_never_contacted(
    app: FastAPI, auth_client: TestClient, address: str
) -> None:
    requests: list[httpx.Request] = []
    use_site(app, recording(requests), {"intranet.test": [PUBLIC_ADDRESS, address]})

    response = read_link(auth_client, "http://intranet.test/admin")

    refused(response, 400, "validation_error", PUBLIC_ONLY)
    assert requests == []


def test_a_public_page_that_redirects_to_a_private_one(
    app: FastAPI, auth_client: TestClient
) -> None:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(302, headers={"location": "http://metadata.test/latest/meta-data/"})

    use_site(app, handler, {"metadata.test": ["169.254.169.254"]})

    refused(read_link(auth_client, "https://public.test/"), 400, "validation_error", PUBLIC_ONLY)
    assert hosts == ["public.test"]


@pytest.mark.parametrize(
    "url",
    [
        "https://user:secret@site.test/page",
        "https://user@site.test/page",
        "http://public.test@127.0.0.1/",
        "file:///etc/passwd",
        "ftp://site.test/report.pdf",
        "javascript:alert(1)",
        "www.site.test/page",
        "/relative/path",
        "http://[abc/",
        "http://site.test:99999/",
    ],
)
def test_anything_but_a_plain_web_address_is_never_fetched(
    app: FastAPI, auth_client: TestClient, url: str
) -> None:
    requests: list[httpx.Request] = []
    use_site(app, recording(requests))

    refused(read_link(auth_client, url), 400, "validation_error", PUBLIC_ONLY)
    assert requests == []


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8783/",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://[64:ff9b::7f00:1]/",
    ],
)
def test_private_addresses_stay_refused_when_integrations_may_use_them(
    app: FastAPI, auth_client: TestClient, url: str
) -> None:
    # INTEGRATIONS_ALLOW_PRIVATE_NETWORK lets local MCP servers in; never a page import.
    # The real downloader runs: these hosts are addresses, so no DNS server is asked.
    local = TEST_SETTINGS.model_copy(update={"integrations_allow_private_network": True})
    app.dependency_overrides[app_settings] = lambda: local

    refused(read_link(auth_client, url), 400, "validation_error", PUBLIC_ONLY)


def test_a_rebinding_dns_server_never_steers_the_connection(
    app: FastAPI, auth_client: TestClient
) -> None:
    # Public for the check, the metadata address when the connection is made.
    network = FakeNetwork(body=b"cloud credentials")
    use_network(app, network, changing([PUBLIC_ADDRESS], ["169.254.169.254"]))

    response = read_link(auth_client, "http://rebind.test/latest/meta-data/")

    refused(response, 400, "validation_error", PUBLIC_ONLY)
    assert network.connected == []


def test_the_page_comes_from_the_address_that_was_checked(
    app: FastAPI, auth_client: TestClient
) -> None:
    network = FakeNetwork(body=b"public page")
    use_network(app, network, resolver({}))

    assert read_link(auth_client, "https://site.test/").json()["text"] == "public page"
    assert network.connected == [PUBLIC_ADDRESS]


# --- the HTTP contract --------------------------------------------------------------


def test_reading_a_link_needs_a_signed_in_user(app: FastAPI, client: TestClient) -> None:
    requests: list[httpx.Request] = []
    use_site(app, recording(requests))

    assert read_link(client, "https://site.test/").status_code == 401
    assert requests == []


@pytest.mark.parametrize(
    "body", [{}, {"url": ""}, {"url": "   "}, {"url": "https://site.test/" + "a" * 2048}]
)
def test_a_missing_or_overlong_link_is_a_validation_error(
    auth_client: TestClient, body: dict[str, str]
) -> None:
    response = auth_client.post("/api/documents/import-url", json=body)

    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"


def test_reading_links_is_rate_limited_per_account(app: FastAPI, auth_client: TestClient) -> None:
    limited = TEST_SETTINGS.model_copy(update={"user_rate_limit_requests": 2})
    app.dependency_overrides[app_settings] = lambda: limited
    use_site(app, serving("A note.", "text/plain"))

    statuses = [read_link(auth_client, "https://site.test/").status_code for _ in range(3)]

    assert statuses == [200, 200, 429]


def test_the_link_never_reaches_the_logs(
    app: FastAPI, auth_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    use_site(app, serving(f"<p>{ARTICLE}</p>", "text/html"), {"gone.test": []})

    with caplog.at_level(logging.INFO):
        read_link(auth_client, "https://site.test/share/token-5f2a9c")
        read_link(auth_client, "https://gone.test/share/token-5f2a9c")

    assert "token-5f2a9c" not in caplog.text
    assert "documents.url_imported outcome=ok format=html" in caplog.text
    assert "documents.url_imported outcome=page_unreachable" in caplog.text


# --- how many links are read at once ---------------------------------------------------


def test_links_read_at_once_are_bounded_and_one_more_is_refused_at_once() -> None:
    """A burst from one account (its whole per-minute allowance at once) holds at most
    DOCUMENT_URL_MAX_CONCURRENT downloads, so as many bodies, in memory."""
    streaming = {"now": 0, "most": 0}

    async def slow_body() -> AsyncIterator[bytes]:
        streaming["now"] += 1
        streaming["most"] = max(streaming["most"], streaming["now"])
        try:
            for _ in range(5):
                await asyncio.sleep(0.01)
                yield ARTICLE.encode()
        finally:
            streaming["now"] -= 1

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=slow_body())

    downloader = PageDownloader(5.0, 5.0, httpx.MockTransport(handler), resolver({}))
    importer = PageImporter(downloader, LIMITS, None, LinkLimits(0, max_links=2))
    allowance = Settings.model_fields["user_rate_limit_requests"].default
    links = [f"https://s{n}.test/a.txt" for n in range(allowance)]

    async def burst() -> list[object]:
        return await asyncio.gather(*map(importer.read, links), return_exceptions=True)

    outcomes = asyncio.run(burst())

    assert streaming["most"] == 2
    refusals = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
    assert len(refusals) == len(links) - 2
    assert all(isinstance(refusal, DocumentReadersBusy) for refusal in refusals)
    assert asyncio.run(importer.read("https://later.test/a.txt")).characters > 0  # slots freed


def test_a_link_past_the_limit_gets_the_busy_answer(app: FastAPI, auth_client: TestClient) -> None:
    one_link = TEST_SETTINGS.model_copy(update={"document_url_max_concurrent": 1})
    app.dependency_overrides[app_settings] = lambda: one_link
    use_site(app, serving(ARTICLE, "text/plain"))

    with extraction_slot(1, 60.0, SlotPool.LINKS):  # another link is being read
        busy = read_link(auth_client, "https://site.test/")

    refused(
        busy,
        503,
        "documents_busy",
        "The server is busy reading other documents. Try again in a moment.",
    )
    assert busy.headers["retry-after"] == "1"
    assert read_link(auth_client, "https://site.test/").status_code == 200
