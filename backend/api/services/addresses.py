"""Is a host safe for the server to connect to? The SSRF guard shared by the
``fetch_url`` tool and users' own MCP servers (AGENTS.md §3, §6).

A host passes only when it resolves and every address it resolves to is
global: never loopback, private, link-local (which covers the cloud metadata
address 169.254.169.254), shared, reserved, multicast, site-local or
IPv4-compatible. An IPv6 address that carries an IPv4 address — IPv4-mapped,
NAT64 (64:ff9b::/96) or 6to4 — is judged as the IPv4 address it carries.

These checks are only half of the guard: ``api.services.outbound`` connects to
the very addresses it checked, so a DNS server cannot answer "public" here and
"internal" when the connection is made (DNS rebinding).
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable

Resolver = Callable[[str], Awaitable[list[str]]]

#: Never public, whatever ``is_global`` says on this Python version.
NEVER_PUBLIC = (
    ipaddress.IPv6Network("::/96"),  # IPv4-compatible, deprecated
    ipaddress.IPv6Network("fec0::/10"),  # site-local, deprecated
    ipaddress.IPv6Network("64:ff9b:1::/48"),  # local-use NAT64
)
#: The well-known NAT64 prefix: the last 32 bits are the IPv4 address reached.
NAT64 = ipaddress.IPv6Network("64:ff9b::/96")


class AddressNotAllowed(ValueError):
    """The host does not resolve, or resolves to an address that is not public."""


async def resolve_host(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def _carried_ipv4(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    if ip in NAT64:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip.ipv4_mapped or ip.sixtofour


def is_public(address: str) -> bool:
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address):
        if any(ip in network for network in NEVER_PUBLIC):
            return False
        ip = _carried_ipv4(ip) or ip
    return ip.is_global and not ip.is_multicast


async def resolve(host: str, resolver: Resolver = resolve_host) -> list[str]:
    """``host``'s addresses, or ``AddressNotAllowed`` when it has none. A name
    no resolver accepts (a label over 63 characters fails IDNA encoding with
    ``UnicodeError``) is refused the same way as one that does not exist."""
    try:
        addresses = await resolver(host)
    except (OSError, ValueError) as cause:  # UnicodeError is a ValueError
        raise AddressNotAllowed(f"Could not resolve {host}.") from cause
    if not addresses:
        raise AddressNotAllowed(f"Could not resolve {host}.")
    return addresses


async def public_addresses(host: str, resolver: Resolver = resolve_host) -> list[str]:
    """Every address ``host`` resolves to, when all of them are public; else
    ``AddressNotAllowed`` with a message that names the host."""
    addresses = await resolve(host, resolver)
    if not all(is_public(address) for address in addresses):
        raise AddressNotAllowed(f"{host} is not a public address.")
    return addresses


async def ensure_public_host(host: str, resolver: Resolver = resolve_host) -> None:
    """Return when every address ``host`` resolves to is public."""
    await public_addresses(host, resolver)
