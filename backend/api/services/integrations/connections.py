"""Every MCP server one user's agents may use: the operator's MCP_SERVERS plus the
user's enabled integrations. The chat agent, pipeline step agents and the tool
catalogue all get them from ``mcp_connections_for`` (AGENTS.md §3).

A user's server is reached through ``GuardedClientFactory``: every connection
— discovery and each tool call open their own session — resolves the host,
is refused unless every address is public, and goes to one of exactly those
addresses; every response is cut off past MCP_MAX_RESPONSE_BYTES
(``api.services.outbound``). Operator servers are trusted configuration and
keep the SDK's default client.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpcore
import httpx
from langchain_mcp_adapters.sessions import Connection
from pydantic import ValidationError

from api.db import Database
from api.exceptions import ValidationFailed
from api.models import Integration, User
from api.repositories import integrations as repository
from api.security import SecretBox, UnreadableSecret
from api.services.integrations.headers import reveal
from api.services.integrations.rules import IntegrationRules, check_url, rules_from
from api.services.mcp import MCPConnections, connection, connections
from api.services.outbound import OutboundPolicy, guarded_client, guarded_transport
from config.settings import HttpMCPServer, Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GuardedClientFactory:
    """HTTP clients that connect only to addresses checked as public at connect
    time and read bounded bodies (SSRF, AGENTS.md §6). Matches the MCP SDK's
    ``McpHttpClientFactory``; ``network`` opens sockets, a fake in tests."""

    timeout_seconds: float
    policy: OutboundPolicy
    network: httpcore.AsyncNetworkBackend | None = None

    def __call__(
        self,
        headers: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
        auth: httpx.Auth | None = None,
    ) -> httpx.AsyncClient:
        return guarded_client(
            guarded_transport(self.policy, self.network),
            headers=headers,
            timeout=timeout or httpx.Timeout(self.timeout_seconds),
            auth=auth,
        )


def integration_connection(
    integration: Integration, box: SecretBox, rules: IntegrationRules
) -> Connection:
    """The adapter connection for one saved integration, streamable HTTP only.

    Raises ``ValidationFailed`` when its URL is no longer allowed and
    ``UnreadableSecret`` when its header values cannot be decrypted.
    """
    check_url(integration.url, rules.addresses)
    try:
        server = HttpMCPServer.model_validate(
            {
                "transport": "streamable_http",
                "url": integration.url,
                "headers": reveal(box, integration),
            }
        )
    except ValidationError as cause:
        raise ValidationFailed("That server URL is not valid.") from cause
    addresses = rules.addresses
    policy = OutboundPolicy(addresses.resolver, addresses.allow_private, rules.max_response_bytes)
    return connection(
        server, rules.timeout_seconds, GuardedClientFactory(rules.timeout_seconds, policy)
    )


def _usable(integration: Integration, box: SecretBox, rules: IntegrationRules) -> Connection | None:
    """The integration's connection, or None (logged) when it cannot be used now."""
    if integration.name in rules.reserved_names:
        reason = "name_taken"
    else:
        try:
            return integration_connection(integration, box, rules)
        except (ValidationFailed, UnreadableSecret) as cause:
            reason = type(cause).__name__
    logger.warning(
        "integration.skipped user_id=%s integration=%s reason=%s",
        integration.user_id,
        integration.name,
        reason,
    )
    return None


def mcp_connections_for(database: Database, user: User, settings: Settings) -> MCPConnections:
    """The operator's MCP_SERVERS plus ``user``'s enabled integrations."""
    with database.session() as session:
        rows = repository.enabled_for(session, user)
    rules = rules_from(settings)
    box = SecretBox(settings.secret_key)
    own = {row.name: usable for row in rows if (usable := _usable(row, box, rules)) is not None}
    return MCPConnections(
        operator=connections(settings.mcp_servers, settings.mcp_timeout_seconds),
        user=own,
        result_max_chars=settings.mcp_tool_result_max_chars,
    )
