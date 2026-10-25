"""Web tools: Tavily search, and page fetches that only ever reach public hosts.

Every test runs over httpx.MockTransport and a fake resolver — no network.
"""

from __future__ import annotations

import gzip
import json
import tracemalloc
from collections.abc import Awaitable, Callable
from dataclasses import replace
from time import perf_counter

import anyio
import httpx
import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import ToolException

from api.services.outbound import OutboundPolicy, guarded_transport
from api.services.toolbox.config import toolbox_config
from api.services.toolbox.tools import TRUNCATED_NOTE, fetch_url_tool, web_search_tool
from api.services.toolbox.web import MAX_REDIRECTS, WebGateway
from tests.conftest import TEST_SETTINGS, UNUSED_WORKSPACE, tool_call
from tests.network_fakes import FakeNetwork, changing

CONFIG = replace(toolbox_config(TEST_SETTINGS, UNUSED_WORKSPACE), search_api_key="tvly-secret")
PUBLIC_ADDRESS = "93.184.215.14"

Handler = Callable[[httpx.Request], httpx.Response]


def resolver(table: dict[str, list[str]]) -> Callable[[str], Awaitable[list[str]]]:
    async def resolve(host: str) -> list[str]:
        return table.get(host, [PUBLIC_ADDRESS])

    return resolve


def gateway(handler: Handler, hosts: dict[str, list[str]] | None = None) -> WebGateway:
    return WebGateway(CONFIG, httpx.MockTransport(handler), resolver(hosts or {}))


def recording(requests: list[httpx.Request]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="should never be fetched")

    return handler


@pytest.mark.asyncio
async def test_web_search_sends_the_key_and_formats_hits() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        hit = {"title": "AIMIx", "url": "https://aimix.test", "content": "Agent pipelines."}
        return httpx.Response(200, json={"results": [hit]})

    result = await web_search_tool(gateway(handler)).ainvoke({"query": "aimix"})

    assert result == "1. AIMIx\nURL: https://aimix.test\nAgent pipelines."
    assert str(requests[0].url) == TEST_SETTINGS.tavily_search_url
    assert requests[0].headers["authorization"] == "Bearer tvly-secret"
    assert json.loads(requests[0].content) == {
        "query": "aimix",
        "max_results": TEST_SETTINGS.web_search_max_results,
        "search_depth": "basic",
    }


@pytest.mark.asyncio
async def test_web_search_failure_is_an_error_result_without_the_key() -> None:
    tool = web_search_tool(gateway(lambda request: httpx.Response(401, json={"detail": "no"})))
    message = await tool.ainvoke(tool_call("web_search", {"query": "aimix"}))
    assert isinstance(message, ToolMessage)
    assert message.status == "error"
    assert "HTTP 401" in str(message.content)
    assert "tvly-secret" not in str(message.content)


@pytest.mark.asyncio
async def test_web_search_rejects_an_unexpected_body() -> None:
    with pytest.raises(ToolException, match="unexpected response"):
        await gateway(lambda request: httpx.Response(200, json=[])).search("aimix")


@pytest.mark.asyncio
async def test_fetch_url_returns_the_readable_text_of_a_page() -> None:
    page = "<p>Hello <b>agents</b></p><script>track()</script>"
    tool = fetch_url_tool(gateway(lambda request: httpx.Response(200, html=page)))
    result = await tool.ainvoke({"url": "https://site.test/page"})
    assert result == "URL: https://site.test/page\n\nHello agents"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1", "::ffff:127.0.0.1", "fe80::1%2"]
)
async def test_fetch_url_refuses_non_public_addresses(address: str) -> None:
    requests: list[httpx.Request] = []
    web = gateway(recording(requests), {"internal.test": [PUBLIC_ADDRESS, address]})
    with pytest.raises(ToolException, match="not a public address"):
        await web.fetch("http://internal.test/admin")
    assert requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://site.test/x", "/relative/path"])
async def test_fetch_url_refuses_other_schemes(url: str) -> None:
    requests: list[httpx.Request] = []
    with pytest.raises(ToolException, match="http or https"):
        await gateway(recording(requests)).fetch(url)
    assert requests == []


@pytest.mark.asyncio
async def test_fetch_url_checks_every_redirect_hop() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "public.test":
            return httpx.Response(302, headers={"location": "http://metadata.test/latest"})
        return httpx.Response(200, text="cloud credentials")

    web = gateway(handler, {"metadata.test": ["169.254.169.254"]})
    with pytest.raises(ToolException, match=r"metadata\.test is not a public address"):
        await web.fetch("https://public.test/")


@pytest.mark.asyncio
async def test_fetch_url_follows_public_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return httpx.Response(200, text="moved here")

    page = await gateway(handler).fetch("https://site.test/old")
    assert (page.url, page.text) == ("https://site.test/new", "moved here")


@pytest.mark.asyncio
async def test_fetch_url_stops_a_redirect_loop() -> None:
    web = gateway(lambda request: httpx.Response(302, headers={"location": "/again"}))
    with pytest.raises(ToolException, match=f"more than {MAX_REDIRECTS} times"):
        await web.fetch("https://site.test/")


@pytest.mark.asyncio
async def test_fetch_url_refuses_binary_content() -> None:
    pdf = httpx.Response(200, content=b"%PDF-1.7", headers={"content-type": "application/pdf"})
    with pytest.raises(ToolException, match="application/pdf, not text"):
        await gateway(lambda request: pdf).fetch("https://site.test/report.pdf")


@pytest.mark.asyncio
async def test_fetch_url_caps_the_download_and_the_text() -> None:
    body = "a" * (TEST_SETTINGS.web_fetch_max_bytes * 3)
    tool = fetch_url_tool(gateway(lambda request: httpx.Response(200, text=body)))
    result = await tool.ainvoke({"url": "https://site.test/big"})
    text = result.removeprefix("URL: https://site.test/big\n\n")
    assert text == "a" * TEST_SETTINGS.web_fetch_max_chars + TRUNCATED_NOTE


@pytest.mark.asyncio
async def test_fetch_url_timeout_is_an_error_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    message = await fetch_url_tool(gateway(handler)).ainvoke(
        tool_call("fetch_url", {"url": "https://slow.test/"})
    )
    assert isinstance(message, ToolMessage)
    assert message.status == "error"
    assert "timed out" in str(message.content)


@pytest.mark.asyncio
async def test_fetch_url_never_connects_where_dns_points_after_the_check() -> None:
    # A rebinding DNS server: public for the check, the metadata address after it.
    lookups = changing([PUBLIC_ADDRESS], ["169.254.169.254"])
    network = FakeNetwork()
    web = WebGateway(CONFIG, guarded_transport(OutboundPolicy(lookups), network), lookups)

    with pytest.raises(ToolException, match=r"rebind\.test is not a public address"):
        await web.fetch("http://rebind.test/latest/meta-data/")

    assert network.connected == []


@pytest.mark.asyncio
async def test_fetch_url_connects_to_the_checked_address() -> None:
    network = FakeNetwork(body=b"public page")
    lookups = resolver({})
    web = WebGateway(CONFIG, guarded_transport(OutboundPolicy(lookups), network), lookups)

    page = await web.fetch("https://site.test/")

    assert page.text == "public page"
    assert network.connected == [PUBLIC_ADDRESS]


@pytest.mark.asyncio
async def test_fetch_url_reads_a_gzip_bomb_within_bounded_memory() -> None:
    bomb = gzip.compress(b"a" * 30_000_000)  # about 30 KB on the wire
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        headers = {"content-encoding": "gzip", "content-type": "text/plain"}
        return httpx.Response(200, stream=httpx.ByteStream(bomb), headers=headers)

    tracemalloc.start()
    try:
        page = await gateway(handler).fetch("https://site.test/bomb")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert (page.text, page.truncated) == ("a" * TEST_SETTINGS.web_fetch_max_chars, True)
    assert peak < 5_000_000
    assert requests[0].headers["accept-encoding"] == "identity"


@pytest.mark.asyncio
async def test_fetch_url_refuses_an_encoding_it_cannot_bound() -> None:
    brotli = httpx.Response(
        200, stream=httpx.ByteStream(b"\x1b"), headers={"content-encoding": "br"}
    )
    with pytest.raises(ToolException, match="DecodingError"):
        await gateway(lambda request: brotli).fetch("https://site.test/")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "charset",
    ["zlib", "rot13", "hex", "base64", "bz2", "idna", "punycode", "undefined", "no-such-charset"],
)
async def test_fetch_url_reads_a_page_whatever_charset_it_claims(charset: str) -> None:
    headers = {"content-type": f"text/plain; charset={charset}"}
    page = httpx.Response(200, content="café".encode(), headers=headers)

    assert (await gateway(lambda request: page).fetch("https://site.test/")).text == "café"


@pytest.mark.asyncio
async def test_fetch_url_still_honours_a_real_charset() -> None:
    headers = {"content-type": "text/plain; charset=latin-1"}
    page = httpx.Response(200, content="café".encode("latin-1"), headers=headers)

    assert (await gateway(lambda request: page).fetch("https://site.test/")).text == "café"


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["http://[abc/", "http://site.test:99999/"])
async def test_fetch_url_refuses_a_malformed_url(url: str) -> None:
    requests: list[httpx.Request] = []
    with pytest.raises(ToolException, match="not a valid URL"):
        await gateway(recording(requests)).fetch(url)
    assert requests == []


@pytest.mark.asyncio
async def test_fetch_url_refuses_a_malformed_redirect() -> None:
    moved = httpx.Response(302, headers={"location": "http://[abc/"})
    with pytest.raises(ToolException, match="redirected to an invalid URL"):
        await gateway(lambda request: moved).fetch("https://site.test/")


@pytest.mark.asyncio
async def test_fetch_url_gives_up_at_its_overall_deadline() -> None:
    async def drip(request: httpx.Request) -> httpx.Response:
        await anyio.sleep(0.3)  # each hop well within WEB_TIMEOUT_SECONDS
        return httpx.Response(302, headers={"location": "/next"})

    web = WebGateway(
        replace(CONFIG, fetch_max_seconds=0.2), httpx.MockTransport(drip), resolver({})
    )
    started = perf_counter()

    message = await fetch_url_tool(web).ainvoke(
        tool_call("fetch_url", {"url": "https://drip.test/"})
    )

    assert isinstance(message, ToolMessage)
    assert message.status == "error"
    assert "took longer than 0.2 seconds" in str(message.content)
    assert perf_counter() - started < 1
