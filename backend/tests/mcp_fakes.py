"""Offline stand-ins for DNS and MCP servers, shared by the integration tests.

Nothing here touches the network: a resolver answers from a table, and
``FakeServers`` replaces ``MultiServerMCPClient`` in ``api.services.mcp_discovery``.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

from api.services.addresses import Resolver

PUBLIC_ADDRESS = "93.184.215.14"
TOOL_DESCRIPTION = "Does a thing."

#: A host's addresses, or the error its lookup raises (OSError, UnicodeError).
DnsAnswer = list[str] | Exception


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    return True


def resolver(table: dict[str, DnsAnswer]) -> Resolver:
    """Answers from ``table``; an IP literal resolves to itself, any other host to a
    public address. The table is read at call time, so a test can change it."""

    async def resolve(host: str) -> list[str]:
        answer = table.get(host, [host] if _is_ip(host) else [PUBLIC_ADDRESS])
        if isinstance(answer, Exception):
            raise answer
        return answer

    return resolve


def fake_tool(name: str, description: str = TOOL_DESCRIPTION) -> BaseTool:
    return StructuredTool.from_function(func=lambda: "done", name=name, description=description)


#: A server's tool names (unprefixed), or the error connecting to it raises.
ServerBehaviour = list[str] | BaseException


class FakeServers:
    """Replaces ``MultiServerMCPClient``: each server name answers from ``behaviour``.

    ``seen`` keeps every connection a client was built with, so tests can check
    the URL, headers and HTTP client factory that would have been used, and
    ``interceptors`` the tool-call interceptors each server's client got.
    """

    def __init__(self, behaviour: dict[str, ServerBehaviour]) -> None:
        self.behaviour = behaviour
        self.seen: dict[str, Any] = {}
        self.interceptors: dict[str, list[Any] | None] = {}

    def __call__(
        self,
        connections: dict[str, Any],
        *,
        tool_name_prefix: bool,
        tool_interceptors: list[Any] | None = None,
    ) -> _FakeClient:
        assert tool_name_prefix is True
        self.seen.update(connections)
        self.interceptors.update(dict.fromkeys(connections, tool_interceptors))
        return _FakeClient(self.behaviour, list(connections))


class _FakeClient:
    def __init__(self, behaviour: dict[str, ServerBehaviour], names: list[str]) -> None:
        self._behaviour = behaviour
        self._names = names

    async def get_tools(self) -> list[BaseTool]:
        tools: list[BaseTool] = []
        for name in self._names:
            outcome = self._behaviour[name]
            if isinstance(outcome, BaseException):
                raise outcome
            tools.extend(fake_tool(f"{name}_{tool}") for tool in outcome)
        return tools
