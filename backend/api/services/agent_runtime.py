"""Shared tool policy and failure contract for chat and pipeline agents."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import openai
from exceptiongroup import ExceptionGroup
from langchain_core.tools import BaseTool, ToolException
from langchain_mcp_adapters.sessions import Connection
from langgraph.errors import GraphRecursionError
from mcp import McpError
from openrouter.errors import NoResponseError, OpenRouterError

from api.exceptions import DomainError, ProviderTimedOut, ProviderUnavailable, ToolUnavailable
from api.services.tool_catalog import discover_tools

AGENT_FAILURES = (
    TimeoutError,
    httpx.TimeoutException,
    openai.APITimeoutError,
    McpError,
    ExceptionGroup,
    httpx.HTTPError,
    openai.APIError,
    OpenRouterError,
    NoResponseError,
    GraphRecursionError,
    ToolException,
)


@dataclass(frozen=True)
class AgentLimits:
    timeout_seconds: float
    recursion_limit: int
    mcp_timeout_seconds: float


@dataclass(frozen=True)
class AgentToolset:
    mcp_connections: dict[str, Connection]
    native_tools: list[BaseTool]


def as_agent_error(cause: Exception) -> DomainError:
    """Translate third-party failures to the application's error contract."""
    if isinstance(cause, (TimeoutError, httpx.TimeoutException, openai.APITimeoutError)):
        return ProviderTimedOut("The agent timed out.")
    if isinstance(cause, (McpError, ExceptionGroup, ToolException)):
        return ToolUnavailable("An MCP server or tool is unavailable.")
    return ProviderUnavailable("The agent could not complete the request.")


async def resolve_tools(
    toolset: AgentToolset, allowed: list[str] | None, timeout_seconds: float
) -> list[BaseTool]:
    """Apply one tool policy to native and configured MCP tools."""
    if allowed == []:
        return []
    native = toolset.native_tools
    if allowed is not None and set(allowed) <= {item.name for item in native}:
        return [item for item in native if item.name in allowed]
    tools = await discover_tools(toolset.mcp_connections, native, timeout_seconds)
    if allowed is None:
        return tools
    selected = [item for item in tools if item.name in allowed]
    if len(selected) != len(allowed):
        raise ToolUnavailable("A selected agent tool is unavailable.")
    return selected
