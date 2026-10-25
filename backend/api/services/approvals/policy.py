"""Which tool calls must ask the run's owner first, resolved in one place.

``approval_policy_for`` reads the settings and the user's integrations once
per agent; the agent only consults the resulting value. A tool asks first
when its source asks — the operator's MCP servers (MCP_REQUIRE_APPROVAL), or
one of the user's integrations whose "Ask me before its tools act" is on — or
when AGENT_APPROVAL_TOOLS names it (meant for built-in tools, such as
``save_artifact``; any tool's full name works).
"""

from __future__ import annotations

from dataclasses import dataclass

from api.db import Database
from api.models import User
from api.repositories import integrations as integration_repository
from api.services.tool_catalog import OPERATOR_MCP_SOURCE
from config.settings import Settings


@dataclass(frozen=True)
class ApprovalPolicy:
    """What asks first (§7 Value Object). The default asks for nothing."""

    #: Sources, as ``tool_catalog.source_of`` names them, whose every tool asks.
    sources: frozenset[str] = frozenset()
    #: Tools that ask whatever their source (AGENT_APPROVAL_TOOLS).
    tool_names: frozenset[str] = frozenset()

    def asks(self, tool_name: str, source: str) -> bool:
        return source in self.sources or tool_name in self.tool_names


NO_APPROVALS = ApprovalPolicy()


def approval_policy_for(database: Database, user: User, settings: Settings) -> ApprovalPolicy:
    """The policy for ``user``'s agents: the settings plus their enabled integrations."""
    with database.session() as session:
        integrations = integration_repository.enabled_for(session, user)
    sources = {row.name for row in integrations if row.require_approval}
    if settings.mcp_require_approval:
        sources.add(OPERATOR_MCP_SOURCE)
    return ApprovalPolicy(frozenset(sources), frozenset(settings.agent_approval_tools))
