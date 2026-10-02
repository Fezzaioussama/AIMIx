"""Discover the tools available to one authenticated pipeline agent."""

from __future__ import annotations

import asyncio
import logging

import anyio
import httpx
from exceptiongroup import ExceptionGroup
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import Connection
from mcp import McpError

from api.db import Database
from api.exceptions import ToolUnavailable
from api.models import User
from api.services.agent_tools import read_only_tools
from api.services.agent_types import ToolDescriptor
from api.services.mcp import connections
from config.settings import get_settings

logger = logging.getLogger(__name__)


async def discover_tools(
    configured: dict[str, Connection], native: list[BaseTool], timeout_seconds: float
) -> list[BaseTool]:
    """Load MCP tools once per agent run; native tools stay available without MCP."""
    if not configured:
        return native
    client = MultiServerMCPClient(configured, tool_name_prefix=True)
    try:
        with anyio.fail_after(timeout_seconds):
            mcp_tools = await client.get_tools()
    except (TimeoutError, McpError, ExceptionGroup, httpx.HTTPError) as cause:
        logger.warning("agent.mcp_discovery_failed error=%s", type(cause).__name__)
        raise ToolUnavailable("An MCP server is unavailable.") from cause
    tools = [*native, *mcp_tools]
    if len({item.name for item in tools}) != len(tools):
        raise ToolUnavailable("Configured tools have duplicate names.")
    return tools


class PipelineToolCatalog:
    def __init__(self, database: Database, user: User) -> None:
        self._database = database
        self._user = user

    async def available(self) -> list[ToolDescriptor]:
        settings = get_settings()
        native = read_only_tools(self._database, self._user)
        tools = await discover_tools(
            connections(settings.mcp_servers, settings.mcp_timeout_seconds),
            native,
            settings.mcp_timeout_seconds,
        )
        native_names = {item.name for item in native}
        limit = settings.agent_tool_description_max_chars
        return [
            ToolDescriptor(
                item.name,
                item.description.strip()[:limit],
                "AIMIx" if item.name in native_names else "MCP",
            )
            for item in tools
        ]

    def available_sync(self) -> list[ToolDescriptor]:
        return asyncio.run(self.available())
