"""Is a host safe for the server to connect to? The SSRF guard shared by the
``fetch_url`` tool and users' own MCP servers (AGENTS.md §3, §6).

A host passes only when it resolves and every address it resolves to is
global: never loopback, private, link-local (which covers the cloud metadata
address 169.254.169.254), shared or reserved. An IPv4-mapped IPv6 address is
judged as the IPv4 address it carries.

The check resolves the name itself and the HTTP client resolves it again when
it connects. A DNS server that answers differently the second time (DNS
rebinding) can slip through that gap, so callers check right before each
connection and document the window that remains.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable

Resolver = Callable[[str], Awaitable[list[str]]]


class AddressNotAllowed(ValueError):
    """The host does not resolve, or resolves to an address that is not public."""


async def resolve_host(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global


async def ensure_public_host(host: str, resolver: Resolver = resolve_host) -> None:
    """Return when every address ``host`` resolves to is public, else raise
    ``AddressNotAllowed`` with a message that names the host."""
    try:
        addresses = await resolver(host)
    except OSError as cause:
        raise AddressNotAllowed(f"Could not resolve {host}.") from cause
    if not addresses or not all(is_public(address) for address in addresses):
        raise AddressNotAllowed(f"{host} is not a public address.")
