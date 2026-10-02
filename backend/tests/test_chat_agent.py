"""Chat agent configuration, MCP discovery, and streaming failure paths."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk, ToolMessage
from pydantic import ValidationError

from api.exceptions import ToolUnavailable
from api.services import agent as agent_service
from api.services.agent import AgentLimits, AgentToolset, LangGraphChatAgent
from api.services.mcp import connections
from config.settings import Settings
from tests.conftest import FakeAgent, use_agent


def test_mcp_servers_are_validated_and_bounded() -> None:
    settings = Settings(
        _env_file=None,
        mcp_servers={
            "docs": {"transport": "streamable_http", "url": "https://example.org/mcp"},
            "local": {"transport": "stdio", "command": "python", "args": ["server.py"]},
        },
    )
    configured = connections(settings.mcp_servers, 7)
    assert configured["docs"]["timeout"] == 7
    assert configured["local"]["command"] == "python"
    assert configured["local"]["session_kwargs"] is not None
    with pytest.raises(ValidationError):
        Settings(_env_file=None, mcp_servers={"bad": {"transport": "stdio", "args": []}})


@pytest.mark.asyncio
async def test_agent_streams_model_text_and_hides_tool_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langchain_core.tools import tool

    captured: dict[str, Any] = {}

    @tool
    def local_tool() -> str:
        """A native tool available alongside MCP tools."""
        return "local"

    class FakeMCPClient:
        def __init__(self, configured: object, *, tool_name_prefix: bool) -> None:
            captured["configured"] = configured
            captured["prefix"] = tool_name_prefix

        async def get_tools(self) -> list[str]:
            return ["example_tool"]

    class FakeGraph:
        async def astream(self, state: object, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            captured["state"] = state
            captured["kwargs"] = kwargs
            yield {
                "type": "messages",
                "data": (
                    ToolMessage(content="secret tool output", tool_call_id="x"),
                    {"langgraph_node": "tools"},
                ),
            }
            yield {
                "type": "messages",
                "data": (AIMessageChunk(content="Hello "), {"langgraph_node": "model"}),
            }
            yield {
                "type": "messages",
                "data": (AIMessageChunk(content="world"), {"langgraph_node": "model"}),
            }

    def fake_create_agent(model: object, tools: object) -> FakeGraph:
        captured["tools"] = tools
        return FakeGraph()

    monkeypatch.setattr(agent_service, "MultiServerMCPClient", FakeMCPClient)
    monkeypatch.setattr(agent_service, "create_agent", fake_create_agent)
    agent = LangGraphChatAgent(object(), AgentToolset({}, [local_tool]), AgentLimits(10, 9))  # type: ignore[arg-type]
    assert [part async for part in agent.stream("hello")] == ["Hello ", "world"]
    assert captured["tools"] == [local_tool, "example_tool"]
    assert captured["prefix"] is True
    assert captured["state"] == {"messages": [{"role": "user", "content": "hello"}]}
    assert captured["kwargs"]["config"] == {"recursion_limit": 9}


@pytest.mark.asyncio
async def test_mcp_discovery_failure_is_a_domain_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingMCPClient:
        def __init__(self, configured: object, *, tool_name_prefix: bool) -> None:
            pass

        async def get_tools(self) -> list[str]:
            raise httpx.ConnectError("offline")

    monkeypatch.setattr(agent_service, "MultiServerMCPClient", FailingMCPClient)
    agent = LangGraphChatAgent(object(), AgentToolset({}, []), AgentLimits(10, 9))  # type: ignore[arg-type]
    with pytest.raises(ToolUnavailable):
        _ = [part async for part in agent.stream("hello")]


def test_chat_empty_reply_is_a_502(app: FastAPI, auth_client: TestClient) -> None:
    use_agent(app, FakeAgent([]))
    response = auth_client.post("/api/chat", json={"prompt": "hello"})
    assert response.status_code == 502
    assert response.json()["error"] == "upstream_response_invalid"


@pytest.mark.asyncio
async def test_langgraph_executes_a_discovered_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool

    called: list[int] = []

    @tool
    def increment(number: int) -> int:
        """Add one to a number."""
        called.append(number)
        return number + 1

    class FakeMCPClient:
        def __init__(self, configured: object, *, tool_name_prefix: bool) -> None:
            pass

        async def get_tools(self) -> list[Any]:
            return [increment]

    monkeypatch.setattr(agent_service, "MultiServerMCPClient", FakeMCPClient)
    monkeypatch.setattr(
        FakeMessagesListChatModel,
        "bind_tools",
        lambda self, tools, **kwargs: self,
        raising=False,
    )
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "increment", "args": {"number": 2}, "id": "call-1"}],
            ),
            AIMessage(content="Result is 3"),
        ]
    )
    agent = LangGraphChatAgent(model, AgentToolset({}, []), AgentLimits(10, 9))
    assert "".join([part async for part in agent.stream("add one to two")]) == "Result is 3"
    assert called == [2]


def test_agent_model_factories_build_offline() -> None:
    from llm.agent_models import create_agent_model
    from llm.base import ProviderConfig
    from llm.exceptions import ProviderNotConfigured

    config = ProviderConfig(api_key="test-key", default_model="test/model", timeout_seconds=1.5)
    assert type(create_agent_model("openrouter", config)).__name__ == "ChatOpenRouter"
    assert type(create_agent_model("togetherai", config)).__name__ == "ChatTogether"
    with pytest.raises(ProviderNotConfigured):
        create_agent_model(
            "openrouter", ProviderConfig(api_key="", default_model="test/model", timeout_seconds=1)
        )


def test_mcp_failure_before_text_has_standard_error_shape(
    app: FastAPI, auth_client: TestClient
) -> None:
    class BrokenAgent:
        async def stream(self, prompt: str) -> AsyncIterator[str]:
            raise ToolUnavailable("An MCP server is unavailable.")
            yield ""  # pragma: no cover - keeps this an async generator

    use_agent(app, BrokenAgent())
    response = auth_client.post("/api/chat", json={"prompt": "hello"})
    assert response.status_code == 502
    assert response.json() == {
        "error": "tool_unavailable",
        "detail": "An MCP server is unavailable.",
    }


def test_mcp_failure_after_text_ends_stream(app: FastAPI, auth_client: TestClient) -> None:
    class BrokenAgent:
        async def stream(self, prompt: str) -> AsyncIterator[str]:
            yield "partial"
            raise ToolUnavailable("An MCP server is unavailable.")

    use_agent(app, BrokenAgent())
    response = auth_client.post("/api/chat", json={"prompt": "hello"})
    assert response.status_code == 200
    assert response.text == "partial"
