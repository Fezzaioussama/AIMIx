"""Load the MCP tools of one agent run (AGENTS.md §7 Adapter over langchain-mcp-adapters).

Operator servers (MCP_SERVERS) are part of the deployment: when one fails,
discovery fails with ``tool_unavailable``, as it always has. A user's own
servers (Settings → Integrations) are optional: each is loaded on its own, and
one that fails is skipped with a logged warning, so runs and chats that do not
need it keep working. A step that selected one of its tools still fails — in
``agent_runtime.resolve_tools``, because the tool is missing.

A user's tool is also dropped, and logged, when its name is already taken or
is not one model APIs accept, so one odd server cannot break every run.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from typing import Any

import anyio
import httpx
from exceptiongroup import BaseExceptionGroup, ExceptionGroup
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import Connection
from mcp import McpError

from api.exceptions import ToolUnavailable
from api.services.addresses import AddressNotAllowed
from api.services.mcp import MCPConnections

logger = logging.getLogger(__name__)

#: ``BaseTool.metadata`` key naming the integration a tool came from.
INTEGRATION_KEY = "aimix_integration"

#: Function names that OpenAI-compatible model APIs accept.
TOOL_NAME_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")

OPERATOR_FAILURES = (TimeoutError, McpError, ExceptionGroup, httpx.HTTPError)

#: HTTP statuses worth explaining; any other is reported by its number.
STATUS_REASONS = {
    401: "it refused the sign-in (HTTP 401), so check the headers",
    403: "it refused access (HTTP 403), so check the headers",
    404: "nothing was found at that URL (HTTP 404)",
}


def _innermost(error: BaseException) -> BaseException:
    """The first real failure inside the task-group wrappers the SDK raises."""
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    return error


def _status_reason(error: httpx.HTTPStatusError) -> str:
    status = error.response.status_code
    return STATUS_REASONS.get(status, f"it answered with HTTP {status}")


#: Failure kind -> plain words for the person (§5 O: a new kind is one entry).
REASONS: tuple[tuple[type[BaseException], Callable[[Any], str]], ...] = (
    (AddressNotAllowed, lambda error: str(error).rstrip(".")),
    (TimeoutError, lambda _: "it did not answer within the time limit"),
    (httpx.TimeoutException, lambda _: "it did not answer within the time limit"),
    (httpx.HTTPStatusError, _status_reason),
    (httpx.ConnectError, lambda _: "the connection to it failed"),
    (McpError, lambda _: "it answered with an MCP error"),
)


def failure_reason(cause: BaseException) -> str:
    error = _innermost(cause)
    for kind, describe in REASONS:
        if isinstance(error, kind):
            return describe(error)
    return "it did not answer as an MCP server"


def failure_kind(cause: BaseException) -> str:
    """The innermost failure's type, for logs: never a URL, header or message."""
    return type(_innermost(cause.__cause__ or cause)).__name__


async def load_server_tools(
    name: str, connection: Connection, timeout_seconds: float
) -> list[BaseTool]:
    """One server's tools, named ``<name>_<tool>``, or ``ToolUnavailable`` saying why not."""
    client = MultiServerMCPClient({name: connection}, tool_name_prefix=True)
    try:
        with anyio.fail_after(timeout_seconds):
            return await client.get_tools()
    except Exception as cause:  # the SDK's failure modes are open-ended; re-raised as ours
        raise ToolUnavailable(f"Could not connect to {name}: {failure_reason(cause)}.") from cause


async def _operator_tools(servers: dict[str, Connection], timeout_seconds: float) -> list[BaseTool]:
    if not servers:
        return []
    client = MultiServerMCPClient(servers, tool_name_prefix=True)
    try:
        with anyio.fail_after(timeout_seconds):
            return await client.get_tools()
    except OPERATOR_FAILURES as cause:
        logger.warning("agent.mcp_discovery_failed error=%s", type(cause).__name__)
        raise ToolUnavailable("An MCP server is unavailable.") from cause


async def _integration_tools(
    name: str, connection: Connection, timeout_seconds: float
) -> list[BaseTool]:
    try:
        tools = await load_server_tools(name, connection, timeout_seconds)
    except ToolUnavailable as cause:
        logger.warning(
            "integration.discovery_skipped integration=%s error=%s", name, failure_kind(cause)
        )
        return []
    for item in tools:
        item.metadata = {**(item.metadata or {}), INTEGRATION_KEY: name}
    return tools


def _admit(taken: set[str], name: str, tools: list[BaseTool]) -> list[BaseTool]:
    """The integration's tools whose names are valid and still free."""
    admitted: list[BaseTool] = []
    for item in tools:
        if TOOL_NAME_PATTERN.fullmatch(item.name) and item.name not in taken:
            taken.add(item.name)
            admitted.append(item)
    if dropped := len(tools) - len(admitted):
        logger.warning("integration.tools_dropped integration=%s count=%d", name, dropped)
    return admitted


def _loaded(outcome: list[BaseTool] | BaseException) -> list[BaseTool]:
    if isinstance(outcome, BaseException):
        raise outcome
    return outcome


async def discover_tools(
    configured: MCPConnections, native: list[BaseTool], timeout_seconds: float
) -> list[BaseTool]:
    """Load MCP tools once per agent run; native tools stay available without MCP."""
    if not configured.operator and not configured.user:
        return native
    names = list(configured.user)
    # Every load is bounded by the timeout; waiting for all leaves no task behind.
    outcomes = await asyncio.gather(
        _operator_tools(configured.operator, timeout_seconds),
        *(_integration_tools(name, configured.user[name], timeout_seconds) for name in names),
        return_exceptions=True,
    )
    operator, *own = (_loaded(outcome) for outcome in outcomes)
    tools = [*native, *operator]
    taken = {item.name for item in tools}
    if len(taken) != len(tools):
        raise ToolUnavailable("Configured tools have duplicate names.")
    for name, batch in zip(names, own, strict=True):
        tools.extend(_admit(taken, name, batch))
    return tools


def integration_of(tool: BaseTool) -> str | None:
    """The integration a discovered tool came from; None for every other tool."""
    source = (tool.metadata or {}).get(INTEGRATION_KEY)
    return source if isinstance(source, str) else None
