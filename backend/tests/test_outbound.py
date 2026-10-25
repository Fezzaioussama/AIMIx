"""The guarded HTTP transport shared by fetch_url and users' MCP servers: which
addresses count as public, connections that go to the address that was
checked (DNS rebinding), no environment proxies, and bounded bodies.

Sockets and DNS are faked (``tests/network_fakes.py``): nothing leaves the process.
"""

from __future__ import annotations

import gzip
import zlib

import httpx
import pytest

from api.services.addresses import AddressNotAllowed, ensure_public_host, is_public
from api.services.integrations.connections import GuardedClientFactory
from api.services.outbound import (
    PIECE_BYTES,
    BoundedBodies,
    OutboundPolicy,
    ResponseTooLarge,
    guarded_client,
    guarded_transport,
)
from tests.mcp_fakes import PUBLIC_ADDRESS, resolver
from tests.network_fakes import FakeNetwork, changing

TOKEN = "Bearer crm-secret-token-1234"


@pytest.mark.parametrize(
    "address",
    [
        "64:ff9b::a9fe:a9fe",  # NAT64 of 169.254.169.254
        "64:ff9b::7f00:1",  # NAT64 of 127.0.0.1
        "64:ff9b:1::1",  # local-use NAT64
        "fec0::1",  # site-local
        "::7f00:1",  # IPv4-compatible 127.0.0.1
        "::a9fe:a9fe",
        "2002:a9fe:a9fe::1",  # 6to4 of 169.254.169.254
        "ff02::1",
        "ff0e::1",  # global-scope multicast
        "224.0.0.1",
        "239.255.255.250",
    ],
)
def test_addresses_that_carry_or_reach_internal_hosts_are_not_public(address: str) -> None:
    assert not is_public(address)


@pytest.mark.parametrize(
    "address", [PUBLIC_ADDRESS, "64:ff9b::5db8:d70e", "2606:4700::1111", "2002:5db8:d70e::1"]
)
def test_public_addresses_stay_public(address: str) -> None:
    assert is_public(address)


@pytest.mark.asyncio
async def test_a_name_no_resolver_accepts_is_refused_not_a_crash() -> None:
    # A label over 63 characters fails IDNA encoding (UnicodeError) before any lookup.
    host = "a" * 64 + ".example"
    with pytest.raises(AddressNotAllowed, match="Could not resolve"):
        await ensure_public_host(host)


def network_client(network: FakeNetwork, policy: OutboundPolicy) -> httpx.AsyncClient:
    return guarded_client(guarded_transport(policy, network))


@pytest.mark.asyncio
async def test_a_connection_goes_to_the_address_that_was_checked() -> None:
    network = FakeNetwork()

    async with network_client(network, OutboundPolicy(resolver({}))) as client:
        response = await client.get("https://site.test/page")

    assert response.text == "ok"
    assert network.connected == [PUBLIC_ADDRESS]
    # TLS and the Host header still name the host, not the address.
    assert network.streams[0].server_hostname == "site.test"
    assert b"host: site.test" in bytes(network.streams[0].written).lower()


@pytest.mark.asyncio
async def test_every_connection_to_an_integration_checks_the_address_it_uses() -> None:
    # A rebinding DNS server: public for the first connection, internal afterwards.
    network = FakeNetwork()
    lookups = changing([PUBLIC_ADDRESS], ["10.0.0.5"])
    factory = GuardedClientFactory(1, OutboundPolicy(lookups), network)

    async with factory(headers={"Authorization": TOKEN}) as client:
        assert client.headers["authorization"] == TOKEN
        assert (await client.post("https://crm.example/mcp")).status_code == 200
    async with factory() as client:
        with pytest.raises(AddressNotAllowed, match=r"crm\.example is not a public address"):
            await client.post("https://crm.example/mcp")

    assert network.connected == [PUBLIC_ADDRESS]


@pytest.mark.asyncio
async def test_environment_proxies_never_carry_a_guarded_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://proxy.test:3128")
    network = FakeNetwork()

    async with GuardedClientFactory(1, OutboundPolicy(resolver({})), network)() as client:
        await client.get("https://crm.example/mcp")

    assert network.connected == [PUBLIC_ADDRESS]


@pytest.mark.asyncio
async def test_an_unreachable_address_falls_back_to_the_next_checked_one() -> None:
    lookups = resolver({"dual.test": ["2606:4700::1111", PUBLIC_ADDRESS]})
    network = FakeNetwork(refuse={"2606:4700::1111"})

    async with network_client(network, OutboundPolicy(lookups)) as client:
        assert (await client.get("https://dual.test/")).text == "ok"

    assert network.connected == ["2606:4700::1111", PUBLIC_ADDRESS]


@pytest.mark.asyncio
async def test_only_local_development_may_connect_to_private_addresses() -> None:
    lookups = resolver({"localhost": ["127.0.0.1"]})
    network = FakeNetwork()

    async with network_client(network, OutboundPolicy(lookups)) as client:
        with pytest.raises(AddressNotAllowed):
            await client.get("http://localhost:9787/mcp")
    async with network_client(network, OutboundPolicy(lookups, allow_private=True)) as client:
        assert (await client.get("http://localhost:9787/mcp")).text == "ok"

    assert network.connected == ["127.0.0.1"]


def encoded(body: bytes, encoding: str) -> httpx.Response:
    """A response as the network delivers it: still encoded, not read yet."""
    return httpx.Response(
        200, stream=httpx.ByteStream(body), headers={"content-encoding": encoding}
    )


def bounded(response: httpx.Response, max_bytes: int | None = None) -> httpx.AsyncClient:
    return guarded_client(BoundedBodies(httpx.MockTransport(lambda request: response), max_bytes))


@pytest.mark.asyncio
async def test_bodies_are_asked_for_unencoded() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["accept-encoding"])
        return httpx.Response(200, text="ok")

    async with guarded_client(BoundedBodies(httpx.MockTransport(handler))) as client:
        await client.get("https://site.test/")

    assert seen == ["identity"]


@pytest.mark.asyncio
async def test_a_compressed_bomb_inflates_in_bounded_pieces() -> None:
    bomb = gzip.compress(b"\0" * 20_000_000)
    response = encoded(bomb, "gzip")
    sizes: list[int] = []

    async with bounded(response) as client, client.stream("GET", "https://site.test/") as page:
        assert "content-encoding" not in page.headers
        async for chunk in page.aiter_bytes():
            sizes.append(len(chunk))
            if sum(sizes) > 1_000_000:
                break

    assert max(sizes) <= PIECE_BYTES


@pytest.mark.asyncio
@pytest.mark.parametrize("encoding", ["gzip", "deflate"])
async def test_gzip_and_deflate_bodies_are_decoded(encoding: str) -> None:
    body = gzip.compress(b"hello") if encoding == "gzip" else zlib.compress(b"hello")
    async with bounded(encoded(body, encoding)) as client:
        assert (await client.get("https://site.test/")).content == b"hello"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"x" * 5_000),
        # Small on the wire, too large once inflated.
        encoded(gzip.compress(b"x" * 5_000), "gzip"),
    ],
)
async def test_a_body_past_the_limit_is_cut_off(response: httpx.Response) -> None:
    async with bounded(response, max_bytes=1_000) as client:
        with pytest.raises(ResponseTooLarge, match="larger than 1000 bytes"):
            await client.get("https://crm.example/mcp")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("encoding", "body"), [("br", b"\x1b"), ("gzip, gzip", b""), ("gzip", b"not gzip")]
)
async def test_unsupported_or_corrupt_encodings_are_refused(encoding: str, body: bytes) -> None:
    async with bounded(encoded(body, encoding)) as client:
        with pytest.raises(httpx.DecodingError):
            await client.get("https://site.test/")
