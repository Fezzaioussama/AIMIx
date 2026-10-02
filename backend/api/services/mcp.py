"""Convert validated MCP configuration into the adapter's connection contract."""

from __future__ import annotations

from datetime import timedelta

from langchain_mcp_adapters.sessions import Connection, StdioConnection, StreamableHttpConnection

from config.settings import HttpMCPServer, MCPServer


def connection(config: MCPServer, timeout_seconds: float) -> Connection:
    session_kwargs = {"read_timeout_seconds": timedelta(seconds=timeout_seconds)}
    if isinstance(config, HttpMCPServer):
        return StreamableHttpConnection(
            transport="streamable_http",
            url=str(config.url),
            headers=config.headers,
            timeout=timeout_seconds,
            sse_read_timeout=timeout_seconds,
            session_kwargs=session_kwargs,
        )
    return StdioConnection(
        transport="stdio",
        command=config.command,
        args=config.args,
        env=config.env or None,
        session_kwargs=session_kwargs,
    )


def connections(servers: dict[str, MCPServer], timeout_seconds: float) -> dict[str, Connection]:
    return {name: connection(server, timeout_seconds) for name, server in servers.items()}
