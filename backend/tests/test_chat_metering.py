"""The chat agent's model calls are counted like a pipeline step's, and the calls
behind one message stop at CHAT_MAX_TOKENS."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from api.exceptions import BudgetExceeded
from api.models import User
from api.services import agent as agent_service
from api.services.agent import ChatMeter, LangGraphChatAgent, get_chat_agent
from api.services.agent_runtime import AgentLimits, AgentToolset
from api.services.llm import LLMProfile
from api.services.mcp import MCPConnections
from api.services.run_budget import RunBudget
from llm.usage import TokenUsage, UsageCallback, metered
from tests.conftest import TEST_SETTINGS


@tool
def increment(number: int) -> int:
    """Add one to a number."""
    return number + 1


def answer(text: str, tokens: int, **extra: Any) -> AIMessage:
    usage = {"input_tokens": tokens, "output_tokens": 0, "total_tokens": tokens}
    return AIMessage(content=text, usage_metadata=usage, **extra)  # type: ignore[arg-type]


def tool_loop() -> FakeMessagesListChatModel:
    """Call 1 (1,200 tokens) asks for the tool; call 2 would answer."""
    return FakeMessagesListChatModel(
        responses=[
            answer("", 1200, tool_calls=[{"name": "increment", "args": {"number": 2}, "id": "1"}]),
            answer("Result is 3", 300),
        ]
    )


@pytest.fixture(autouse=True)
def tools_bind_to_the_fake_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(FakeMessagesListChatModel, "bind_tools", lambda self, tools, **kw: self)


def chat_agent(max_tokens: int | None) -> LangGraphChatAgent:
    model = metered(tool_loop(), UsageCallback(None, ChatMeter(RunBudget(max_tokens=max_tokens))))
    return LangGraphChatAgent(
        model, AgentToolset(MCPConnections(), [increment]), AgentLimits(10, 9, 1)
    )


def test_the_meter_refuses_the_call_after_the_limit_is_reached() -> None:
    meter = ChatMeter(RunBudget(max_tokens=1000))

    meter.before_call()
    meter.after_call(TokenUsage.of(900, 100, None))

    with pytest.raises(BudgetExceeded) as stopped:
        meter.before_call()
    assert stopped.value.detail == (
        "This reply stopped at 1,000 tokens because it reached its 1,000-token limit."
    )


@pytest.mark.asyncio
async def test_a_message_stops_once_its_calls_reach_the_limit() -> None:
    with pytest.raises(BudgetExceeded):
        _ = [part async for part in chat_agent(1000).stream("add one to two")]


@pytest.mark.asyncio
async def test_without_a_limit_the_calls_are_counted_and_never_refused() -> None:
    assert "".join([part async for part in chat_agent(None).stream("add one")]) == "Result is 3"


def test_the_chat_agent_meters_its_model(
    monkeypatch: pytest.MonkeyPatch, app: FastAPI, user: User
) -> None:
    monkeypatch.setattr(agent_service, "get_agent_model", lambda profile: tool_loop())
    profile = LLMProfile("openrouter", TEST_SETTINGS.openrouter_default_model, api_key="k")

    agent = get_chat_agent(app.state.database, user, profile, lambda *_: None)  # type: ignore[arg-type,return-value]

    callbacks = agent._model.callbacks
    assert isinstance(callbacks, list)
    assert any(isinstance(callback, UsageCallback) for callback in callbacks)


def test_a_message_refused_before_its_first_words_is_a_409(
    app: FastAPI, auth_client: TestClient
) -> None:
    from tests.conftest import use_agent

    use_agent(app, chat_agent(1000))

    response = auth_client.post("/api/chat", json={"prompt": "add one to two"})

    assert response.status_code == 409
    assert response.json()["error"] == "budget_exceeded"
