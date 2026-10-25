"""Where a user's MCP server may live, and the limits on integrations (AGENTS.md §6).

Users reach their servers over streamable HTTP only — never stdio, which would
run a command on this server. The URL must use https; plain http is accepted
only when APP_ENV=local. Credentials belong in headers, never in the URL.

Every address the host resolves to must be public (``api.services.addresses``):
checked when the integration is saved, and again by every connection to it,
which then goes to one of exactly the addresses it checked
(``connections.GuardedClientFactory``), so a DNS server that changes its
answer (DNS rebinding) cannot redirect it.

Local development reaches a server on 127.0.0.1 by setting both APP_ENV=local
and INTEGRATIONS_ALLOW_PRIVATE_NETWORK=true; production refuses to start with
the latter, and APP_ENV=test ignores it.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import anyio

from api.exceptions import ValidationFailed
from api.services.addresses import AddressNotAllowed, Resolver, ensure_public_host, resolve_host
from config.settings import Settings


@dataclass(frozen=True)
class AddressPolicy:
    """Which server URLs may be used (§7 Value Object)."""

    allow_http: bool
    allow_private: bool
    resolver: Resolver = resolve_host


@dataclass(frozen=True)
class IntegrationRules:
    """Everything the integration use cases read from settings, copied once (§5 D)."""

    addresses: AddressPolicy
    #: MCP_SERVERS names: a user's integration may not take one.
    reserved_names: frozenset[str]
    max_per_user: int
    timeout_seconds: float
    description_max_chars: int
    #: One HTTP response from a user's server stops past this (MCP_MAX_RESPONSE_BYTES).
    max_response_bytes: int


def rules_from(settings: Settings, resolver: Resolver = resolve_host) -> IntegrationRules:
    local = settings.app_env == "local"
    return IntegrationRules(
        addresses=AddressPolicy(
            allow_http=local,
            allow_private=local and settings.integrations_allow_private_network,
            resolver=resolver,
        ),
        reserved_names=frozenset(settings.mcp_servers),
        max_per_user=settings.integrations_max_per_user,
        timeout_seconds=settings.mcp_timeout_seconds,
        description_max_chars=settings.agent_tool_description_max_chars,
        max_response_bytes=settings.mcp_max_response_bytes,
    )


def check_url(url: str, policy: AddressPolicy) -> str:
    """The URL's host when ``policy`` allows the URL; else ``ValidationFailed``."""
    schemes = ("https", "http") if policy.allow_http else ("https",)
    try:
        parts = urlsplit(url)
        hostname, _port = parts.hostname, parts.port
    except ValueError as cause:
        raise ValidationFailed("That server URL is not valid.") from cause
    if parts.scheme not in schemes or not hostname:
        raise ValidationFailed(f"Enter the full server URL, starting with {' or '.join(schemes)}.")
    if parts.username is not None or parts.password is not None:
        raise ValidationFailed("Put sign-in details in a header, not in the URL.")
    return hostname


def origin(url: str) -> tuple[str, str, int | None]:
    """Scheme, host and port: where saved header values are allowed to go."""
    parts = urlsplit(url)
    return parts.scheme, parts.hostname or "", parts.port


async def ensure_reachable(url: str, policy: AddressPolicy, timeout_seconds: float) -> None:
    """``ValidationFailed`` unless the URL is allowed and its host is public."""
    host = check_url(url, policy)
    if policy.allow_private:
        return
    try:
        with anyio.fail_after(timeout_seconds):
            await ensure_public_host(host, policy.resolver)
    except AddressNotAllowed as cause:
        raise ValidationFailed(f"{cause} Integrations can only reach public servers.") from cause
    except TimeoutError as cause:
        raise ValidationFailed(f"Could not resolve {host} in time.") from cause
