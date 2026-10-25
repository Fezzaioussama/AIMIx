"""The one HTTP transport for requests whose destination a user or a model picks:
``fetch_url`` pages and users' own MCP servers (AGENTS.md §3, §6; §7 Adapter
over httpx and httpcore).

Two layers, each closing a hole the address check alone leaves open:

* ``CheckedNetwork``, an httpcore network backend, resolves the host itself,
  refuses it unless every address is public (``api.services.addresses``) and
  connects to one of exactly those addresses. TLS still verifies the host
  name and the Host header still carries it, but nothing resolves the name a
  second time, so a DNS server cannot answer "public" to the check and
  "169.254.169.254" to the connection (DNS rebinding).
* ``BoundedBodies``, an httpx transport wrapper, asks for unencoded bodies,
  decodes gzip and deflate itself in pieces of at most ``PIECE_BYTES``, refuses
  any other content encoding, and ends a body that grows past
  ``max_response_bytes`` with ``ResponseTooLarge``. A few kilobytes of gzip
  that inflate to gigabytes, or an endless stream, never fill the memory.

Clients built here never read proxy settings from the environment: a proxy
would resolve the name itself, behind the check's back.
"""

from __future__ import annotations

import contextlib
import zlib
from collections.abc import AsyncIterator, Iterable, Iterator
from dataclasses import dataclass
from typing import Any

import anyio
import httpcore
import httpx

from api.services.addresses import (
    AddressNotAllowed,
    Resolver,
    public_addresses,
    resolve,
    resolve_host,
)

#: A decoded body comes in pieces no larger than this, however well it compresses.
PIECE_BYTES = 64 * 1024
#: Content encodings decoded here; anything else is refused.
INFLATED_ENCODINGS = frozenset({"gzip", "x-gzip", "deflate"})
#: zlib reads either a gzip or a zlib header with these window bits.
_GZIP_OR_ZLIB = 32 + zlib.MAX_WBITS


class ResponseTooLarge(httpx.RequestError):
    """A response body went past the transport's byte limit."""


@dataclass(frozen=True)
class OutboundPolicy:
    """Where a guarded client may connect and how much it may read (§7 Value Object)."""

    resolver: Resolver = resolve_host
    #: Local development only (INTEGRATIONS_ALLOW_PRIVATE_NETWORK): any address goes.
    allow_private: bool = False
    #: A longer body raises ``ResponseTooLarge``; None leaves the bound to the caller.
    max_response_bytes: int | None = None


class CheckedNetwork(httpcore.AsyncNetworkBackend):
    """Connects only to the addresses it resolved and checked itself."""

    def __init__(self, policy: OutboundPolicy, network: httpcore.AsyncNetworkBackend) -> None:
        self._policy = policy
        self._network = network

    async def _addresses(self, host: str, timeout: float | None) -> list[str]:
        policy = self._policy
        check = resolve if policy.allow_private else public_addresses
        try:
            with anyio.fail_after(timeout):
                return await check(host, policy.resolver)
        except TimeoutError as cause:
            raise httpcore.ConnectTimeout(f"Resolving {host} timed out.") from cause

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        """Try the checked addresses in order, as connecting by name would (an
        unreachable IPv6 address falls back to the IPv4 one)."""
        *others, last = await self._addresses(host, timeout)
        for address in others:
            with contextlib.suppress(httpcore.ConnectError, httpcore.ConnectTimeout):
                return await self._network.connect_tcp(
                    address, port, timeout, local_address, socket_options
                )
        return await self._network.connect_tcp(last, port, timeout, local_address, socket_options)

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise AddressNotAllowed("Only network addresses can be reached.")

    async def sleep(self, seconds: float) -> None:
        await self._network.sleep(seconds)


class _ConnectingThrough(httpx.AsyncHTTPTransport):
    """httpx's own transport (request and error mapping, pooling) whose
    connections are opened by ``network``."""

    def __init__(self, network: httpcore.AsyncNetworkBackend) -> None:
        ssl_context = httpx.create_ssl_context()
        super().__init__(verify=ssl_context)
        self._pool = httpcore.AsyncConnectionPool(ssl_context=ssl_context, network_backend=network)


class _Inflater:
    """gzip or deflate, decoded in bounded pieces."""

    def __init__(self) -> None:
        self._zlib = zlib.decompressobj(_GZIP_OR_ZLIB)

    def pieces(self, data: bytes) -> Iterator[bytes]:
        try:
            while piece := self._zlib.decompress(data, PIECE_BYTES):
                yield piece
                data = self._zlib.unconsumed_tail
        except zlib.error as cause:
            raise httpx.DecodingError("The response is not valid gzip or deflate data.") from cause


def _inflater(response: httpx.Response, request: httpx.Request) -> _Inflater | None:
    listed = ",".join(response.headers.get_list("content-encoding")).lower().split(",")
    encodings = [item.strip() for item in listed if item.strip() not in ("", "identity")]
    if not encodings:
        return None
    if len(encodings) == 1 and encodings[0] in INFLATED_ENCODINGS:
        return _Inflater()
    raise httpx.DecodingError("The response uses an unsupported content encoding.", request=request)


class _BoundedStream(httpx.AsyncByteStream):
    def __init__(
        self, raw: httpx.AsyncByteStream, inflater: _Inflater | None, max_bytes: int | None
    ) -> None:
        self._raw = raw
        self._inflater = inflater
        self._max_bytes = max_bytes

    async def __aiter__(self) -> AsyncIterator[bytes]:
        size = 0
        async for chunk in self._raw:
            for piece in self._inflater.pieces(chunk) if self._inflater else (chunk,):
                size += len(piece)
                if self._max_bytes is not None and size > self._max_bytes:
                    raise ResponseTooLarge(f"The response was larger than {self._max_bytes} bytes.")
                yield piece

    async def aclose(self) -> None:
        await self._raw.aclose()


class BoundedBodies(httpx.AsyncBaseTransport):
    """Wraps a transport so every body it returns is decoded here, in bounded
    pieces, and stops at ``max_bytes`` (None: no limit beyond the pieces)."""

    def __init__(self, inner: httpx.AsyncBaseTransport, max_bytes: int | None = None) -> None:
        self._inner = inner
        self._max_bytes = max_bytes

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        request.headers["Accept-Encoding"] = "identity"
        response = await self._inner.handle_async_request(request)
        try:
            inflater = _inflater(response, request)
        except httpx.DecodingError:
            await response.aclose()
            raise
        headers = response.headers.copy()
        if inflater is not None:  # what the caller reads is no longer encoded
            for name in ("content-encoding", "content-length"):
                headers.pop(name, None)
        raw = response.stream
        if not isinstance(raw, httpx.AsyncByteStream):  # pragma: no cover - async transports only
            raise TypeError("BoundedBodies wraps async transports only.")
        return httpx.Response(
            response.status_code,
            headers=headers,
            stream=_BoundedStream(raw, inflater, self._max_bytes),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()


def guarded_transport(
    policy: OutboundPolicy, network: httpcore.AsyncNetworkBackend | None = None
) -> httpx.AsyncBaseTransport:
    """Bounded bodies over connections to checked addresses only. ``network``
    opens the sockets: the real one unless a test passes a fake."""
    checked = CheckedNetwork(policy, network or httpcore.AnyIOBackend())
    return BoundedBodies(_ConnectingThrough(checked), policy.max_response_bytes)


def guarded_client(transport: httpx.AsyncBaseTransport, **options: Any) -> httpx.AsyncClient:
    """An httpx client over ``transport`` that ignores proxy and auth settings
    from the environment."""
    return httpx.AsyncClient(transport=transport, trust_env=False, **options)
