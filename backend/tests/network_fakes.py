"""Offline sockets and DNS answers for the guarded HTTP transport
(``api.services.outbound``): nothing here opens a real connection.

``FakeNetwork`` stands in for httpcore's network backend, so a test sees which
address a connection was really opened to, the TLS server name and the bytes
written; ``changing`` is a DNS server that answers differently each time it is
asked (DNS rebinding).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import anyio
import httpcore

from api.services.addresses import Resolver


def http_response(body: bytes = b"ok") -> bytes:
    head = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: %d\r\n\r\n"
    return head % len(body) + body


class FakeStream(httpcore.AsyncNetworkStream):
    """One connection that answers every request with the same canned response."""

    def __init__(self, response: bytes) -> None:
        self._unread = [response]
        self.written = bytearray()
        self.server_hostname: str | None = None

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return self._unread.pop(0) if self._unread else b""

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self.written.extend(buffer)

    async def aclose(self) -> None:
        return None

    async def start_tls(
        self, ssl_context: Any, server_hostname: str | None = None, timeout: float | None = None
    ) -> httpcore.AsyncNetworkStream:
        self.server_hostname = server_hostname
        return self

    def get_extra_info(self, info: str) -> Any:
        return None


class FakeNetwork(httpcore.AsyncNetworkBackend):
    """Records the address of every connection; ``refuse`` fail like a closed port."""

    def __init__(self, body: bytes = b"ok", refuse: Iterable[str] = ()) -> None:
        self._body = body
        self._refuse = set(refuse)
        self.connected: list[str] = []
        self.streams: list[FakeStream] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        self.connected.append(host)
        if host in self._refuse:
            raise httpcore.ConnectError(f"{host} refused the connection")
        stream = FakeStream(http_response(self._body))
        self.streams.append(stream)
        return stream

    async def connect_unix_socket(
        self, path: str, timeout: float | None = None, socket_options: Iterable[Any] | None = None
    ) -> httpcore.AsyncNetworkStream:
        raise AssertionError("never used")

    async def sleep(self, seconds: float) -> None:
        await anyio.sleep(seconds)


def changing(*answers: list[str]) -> Resolver:
    """Gives each answer in turn, then keeps repeating the last one."""
    queue = list(answers)

    async def resolve(host: str) -> list[str]:
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return resolve
