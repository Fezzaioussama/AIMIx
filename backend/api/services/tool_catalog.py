"""Discover the tools available to one authenticated pipeline agent."""

from __future__ import annotations

import asyncio

from langchain_core.tools import BaseTool

from api.db import Database
from api.models import User
from api.services.agent_tools import native_tools
from api.services.agent_types import ToolDescriptor
from api.services.integrations.connections import mcp_connections_for
from api.services.mcp_discovery import discover_tools, integration_of
from config.settings import get_settings

#: Sources shown for tools that are not from one of the user's integrations,
#: whose tools show the integration's name instead.
NATIVE_SOURCE = "AIMIx"
OPERATOR_MCP_SOURCE = "MCP"


def describe(tool: BaseTool, limit: int) -> str:
    """A tool's description as people see it, cut to AGENT_TOOL_DESCRIPTION_MAX_CHARS."""
    return tool.description.strip()[:limit]


class PipelineToolCatalog:
    def __init__(self, database: Database, user: User) -> None:
        self._database = database
        self._user = user

    async def available(self) -> list[ToolDescriptor]:
        settings = get_settings()
        native = native_tools(self._database, self._user, settings)
        tools = await discover_tools(
            mcp_connections_for(self._database, self._user, settings),
            native,
            settings.mcp_timeout_seconds,
        )
        native_names = {item.name for item in native}
        limit = settings.agent_tool_description_max_chars
        return [
            ToolDescriptor(
                item.name,
                describe(item, limit),
                NATIVE_SOURCE
                if item.name in native_names
                else integration_of(item) or OPERATOR_MCP_SOURCE,
            )
            for item in tools
        ]

    def available_sync(self) -> list[ToolDescriptor]:
        return asyncio.run(self.available())
