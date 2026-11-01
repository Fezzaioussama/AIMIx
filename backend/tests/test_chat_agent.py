"""Chat agent configuration, MCP discovery, and streaming failure paths."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from pydantic import ValidationError

from api.exceptions import ToolUnavailable
from api.services import agent as agent_service
from api.services import agent_runtime
from api.services.agent import LangGraphChatAgent
from api.services.agent_runtime import AgentLimits, AgentToolset
from api.services.chat_conversation import ChatTurn, Conversation
from api.services.chat_events import ChatEvent, text_event
from api.services.mcp import MCPConnections, connections
from config.settings import Settings
from tests.conftest import FakeAgent, use_agent
from tests.mcp_fakes import fake_tool


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
    example_tool = fake_tool("example_tool")

    @tool
    def local_tool() -> str:
        """A native tool available alongside MCP tools."""
        return "local"

    async def fake_discover(configured: object, native: list[Any], timeout: float) -> list[Any]:
        captured["configured"] = configured
        return [*native, example_tool]

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

    def fake_create_agent(model: object, tools: object, **kwargs: object) -> FakeGraph:
        captured["tools"] = tools
        return FakeGraph()

    monkeypatch.setattr(agent_runtime, "discover_tools", fake_discover)
    monkeypatch.setattr(agent_service, "create_agent", fake_create_agent)
    agent = LangGraphChatAgent(object(), AgentToolset({}, [local_tool]), AgentLimits(10, 9, 1))  # type: ignore[arg-type]
    events = [part async for part in agent.stream(Conversation("hello"))]
    assert [event.text for event in events if event.kind == "text"] == ["Hello ", "world"]
    assert all("secret tool output" not in f"{event.text}{event.detail}" for event in events)
    assert captured["tools"] == [local_tool, example_tool]
    assert captured["state"] == {"messages": [{"role": "user", "content": "hello"}]}
    assert captured["kwargs"]["config"]["recursion_limit"] == 9


@pytest.mark.asyncio
async def test_mcp_discovery_failure_is_a_domain_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_discover(configured: object, native: list[Any], timeout: float) -> list[Any]:
        raise ToolUnavailable("An MCP server is unavailable.")

    monkeypatch.setattr(agent_runtime, "discover_tools", fake_discover)
    agent = LangGraphChatAgent(object(), AgentToolset({}, []), AgentLimits(10, 9, 1))  # type: ignore[arg-type]
    with pytest.raises(ToolUnavailable):
        _ = [part async for part in agent.stream(Conversation("hello"))]


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

    async def fake_discover(configured: object, native: list[Any], timeout: float) -> list[Any]:
        return [*native, increment]

    monkeypatch.setattr(agent_runtime, "discover_tools", fake_discover)
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
    agent = LangGraphChatAgent(model, AgentToolset({}, []), AgentLimits(10, 9, 1))
    events = [part async for part in agent.stream(Conversation("add one to two"))]
    assert "".join(event.text for event in events if event.kind == "text") == "Result is 3"
    assert [(event.tool, event.status) for event in events if event.kind == "tool"] == [
        ("increment", "started"),
        ("increment", "finished"),
    ]
    assert called == [2]


@pytest.mark.asyncio
async def test_a_refused_tool_is_reported_and_the_reply_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.tools import ToolException, tool

    @tool
    def refuse() -> str:
        """Refuse the write."""
        raise ToolException("A pipeline needs at least one step.")

    monkeypatch.setattr(
        FakeMessagesListChatModel,
        "bind_tools",
        lambda self, tools, **kwargs: self,
        raising=False,
    )
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(content="", tool_calls=[{"name": "refuse", "args": {}, "id": "call-1"}]),
            AIMessage(content="I could not create it."),
        ]
    )
    agent = LangGraphChatAgent(
        model, AgentToolset(MCPConnections(), [refuse]), AgentLimits(10, 9, 1)
    )

    events = [part async for part in agent.stream(Conversation("create it"))]
    assert [(event.tool, event.status) for event in events if event.kind == "tool"] == [
        ("refuse", "started"),
        ("refuse", "failed"),
    ]
    assert "".join(event.text for event in events if event.kind == "text") == (
        "I could not create it."
    )


def test_agent_model_factories_build_offline() -> None:
    from langchain_openai import ChatOpenAI
    from langchain_openrouter import ChatOpenRouter
    from langchain_together import ChatTogether

    from llm.agent_models import create_agent_model
    from llm.base import ProviderConfig
    from llm.exceptions import ProviderNotConfigured

    config = ProviderConfig(api_key="test-key", default_model="test/model", timeout_seconds=1.5)
    assert isinstance(create_agent_model("openrouter", config), ChatOpenRouter)
    assert isinstance(create_agent_model("togetherai", config), ChatTogether)
    meta_model: Any = create_agent_model("meta", config)
    assert isinstance(meta_model, ChatOpenAI)
    # Asked for explicitly, or a streamed chat message's calls would go uncounted.
    assert meta_model.stream_usage is True
    with pytest.raises(ProviderNotConfigured):
        create_agent_model(
            "openrouter", ProviderConfig(api_key="", default_model="test/model", timeout_seconds=1)
        )


def test_mcp_failure_before_text_has_standard_error_shape(
    app: FastAPI, auth_client: TestClient
) -> None:
    class BrokenAgent:
        async def stream(self, conversation: Conversation) -> AsyncIterator[ChatEvent]:
            raise ToolUnavailable("An MCP server is unavailable.")
            yield text_event("")  # pragma: no cover - keeps this an async generator

    use_agent(app, BrokenAgent())
    response = auth_client.post("/api/chat", json={"prompt": "hello"})
    assert response.status_code == 502
    assert response.json() == {
        "error": "tool_unavailable",
        "detail": "An MCP server is unavailable.",
    }


def test_mcp_failure_after_text_ends_stream(app: FastAPI, auth_client: TestClient) -> None:
    class BrokenAgent:
        async def stream(self, conversation: Conversation) -> AsyncIterator[ChatEvent]:
            yield text_event("partial")
            raise ToolUnavailable("An MCP server is unavailable.")

    use_agent(app, BrokenAgent())
    response = auth_client.post(
        "/api/chat",
        json={"prompt": "hello"},
        headers={"Accept": "application/x-ndjson"},
    )
    assert response.status_code == 200
    assert [json.loads(line) for line in response.text.splitlines()] == [
        {"type": "text", "text": "partial"}
    ]


@pytest.mark.asyncio
async def test_the_agent_reads_its_instructions_and_the_earlier_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_discover(configured: object, native: list[Any], timeout: float) -> list[Any]:
        return native

    class FakeGraph:
        async def astream(self, state: object, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            captured["state"] = state
            yield {
                "type": "messages",
                "data": (AIMessageChunk(content="Done."), {"langgraph_node": "model"}),
            }

    def fake_create_agent(model: object, tools: object, **kwargs: Any) -> FakeGraph:
        captured["system_prompt"] = kwargs["system_prompt"]
        return FakeGraph()

    monkeypatch.setattr(agent_runtime, "discover_tools", fake_discover)
    monkeypatch.setattr(agent_service, "create_agent", fake_create_agent)
    agent = LangGraphChatAgent(object(), AgentToolset({}, []), AgentLimits(10, 9, 1))  # type: ignore[arg-type]
    earlier = (ChatTurn("user", "Build a news digest"), ChatTurn("assistant", "Done: two agents."))

    _ = [part async for part in agent.stream(Conversation("Weekly", earlier, "Europe/Paris"))]

    assert captured["state"] == {
        "messages": [
            {"role": "user", "content": "Build a news digest"},
            {"role": "assistant", "content": "Done: two agents."},
            {"role": "user", "content": "Weekly"},
        ]
    }
    assert captured["system_prompt"].startswith("You are the AIMIx assistant.")
    assert "in the person's time zone, Europe/Paris" in captured["system_prompt"]
