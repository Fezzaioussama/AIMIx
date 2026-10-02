"""Authenticated native and MCP tool discovery for pipeline builders."""

from __future__ import annotations

from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.tools import tool
from langchain_mcp_adapters.sessions import Connection

from api.exceptions import ToolUnavailable
from api.services import tool_catalog


def test_catalog_endpoint_lists_native_tools_without_mcp(auth_client: TestClient) -> None:
    response = auth_client.get("/api/agent-tools")
    assert response.status_code == 200
    assert {item["name"] for item in response.json()} == {
        "list_pipelines",
        "inspect_pipeline",
    }
    assert {item["source"] for item in response.json()} == {"AIMIx"}


@pytest.mark.asyncio
async def test_mcp_discovery_prefixes_names(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, Any] = {}

    @tool
    def docs_search(query: str) -> str:
        """Search documents."""
        return query

    class FakeMCPClient:
        def __init__(self, configured: object, *, tool_name_prefix: bool) -> None:
            observed["prefix"] = tool_name_prefix

        async def get_tools(self) -> list[Any]:
            return [docs_search]

    monkeypatch.setattr(tool_catalog, "MultiServerMCPClient", FakeMCPClient)
    configured = cast(dict[str, Connection], {"docs": {}})
    discovered = await tool_catalog.discover_tools(configured, [], 1)
    assert [item.name for item in discovered] == ["docs_search"]
    assert observed["prefix"] is True


@pytest.mark.asyncio
async def test_mcp_discovery_failure_is_a_domain_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingMCPClient:
        def __init__(self, configured: object, *, tool_name_prefix: bool) -> None:
            pass

        async def get_tools(self) -> list[Any]:
            raise httpx.ConnectError("offline")

    monkeypatch.setattr(tool_catalog, "MultiServerMCPClient", FailingMCPClient)
    configured = cast(dict[str, Connection], {"docs": {}})
    with pytest.raises(ToolUnavailable):
        await tool_catalog.discover_tools(configured, [], 1)
