"""Convert validated MCP configuration into the adapter's connection contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from langchain_mcp_adapters.sessions import (
    Connection,
    McpHttpClientFactory,
    StdioConnection,
    StreamableHttpConnection,
)

from config.settings import HttpMCPServer, MCPServer


@dataclass(frozen=True)
class MCPConnections:
    """The MCP servers one agent run may use (§7 Value Object).

    ``operator`` comes from MCP_SERVERS and must answer; ``user`` holds the
    signed-in user's enabled integrations, which discovery skips when they fail.
    """

    operator: dict[str, Connection] = field(default_factory=dict)
    user: dict[str, Connection] = field(default_factory=dict)
    #: The text of one tool result the model receives is cut here
    #: (MCP_TOOL_RESULT_MAX_CHARS); None leaves results whole.
    result_max_chars: int | None = None


def connection(
    config: MCPServer, timeout_seconds: float, client_factory: McpHttpClientFactory | None = None
) -> Connection:
    """``client_factory`` builds the HTTP client of an HTTP server, e.g. one that
    checks every request's address; None keeps the SDK's default client."""
    session_kwargs = {"read_timeout_seconds": timedelta(seconds=timeout_seconds)}
    if isinstance(config, HttpMCPServer):
        http = StreamableHttpConnection(
            transport="streamable_http",
            url=str(config.url),
            headers=config.headers,
            timeout=timeout_seconds,
            sse_read_timeout=timeout_seconds,
            session_kwargs=session_kwargs,
        )
        if client_factory is not None:
            http["httpx_client_factory"] = client_factory
        return http
    return StdioConnection(
        transport="stdio",
        command=config.command,
        args=config.args,
        env=config.env or None,
        session_kwargs=session_kwargs,
    )


def connections(servers: dict[str, MCPServer], timeout_seconds: float) -> dict[str, Connection]:
    return {name: connection(server, timeout_seconds) for name, server in servers.items()}
