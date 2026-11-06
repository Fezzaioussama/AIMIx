"""The context guard: an agent's tool loop is kept inside its model's context window,
after Celia Agent's proactive compaction, with the agent's own model writing the
summary of the older messages."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from api.services import agent as agent_service
from api.services import agent_runtime
from api.services.agent import LangGraphChatAgent
from api.services.agent_runtime import (
    AgentLimits,
    AgentToolset,
    ContextBudget,
    context_budget,
    context_guard,
)
from api.services.agent_types import AgentTask
from api.services.chat_conversation import Conversation
from api.services.mcp import MCPConnections
from api.services.multiagent.step_agent import LangGraphStepAgent, StepServices
from llm.catalog import ModelInfo
from tests.conftest import TEST_SETTINGS

#: A 2,000-token window, compacted at half of it, the newest two messages kept.
BUDGET = ContextBudget(window_tokens=2_000, ratio=0.5, keep_messages=2)


@tool
def read_everything() -> str:
    """Read a long document."""
    return "x" * 20_000  # about 5,000 tokens: well past the budget's trigger


def reading_model() -> FakeMessagesListChatModel:
    """Call 1 reads; the guard then asks for a summary; the next call answers."""
    return FakeMessagesListChatModel(
        responses=[
            AIMessage(content="", tool_calls=[{"name": "read_everything", "args": {}, "id": "1"}]),
            AIMessage(content="Notes on what was read."),
            AIMessage(content="Done: 20,000 characters read."),
        ]
    )


@pytest.fixture(autouse=True)
def tools_bind_to_the_fake_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(FakeMessagesListChatModel, "bind_tools", lambda self, tools, **kw: self)


def test_the_budget_takes_the_models_window_else_the_default() -> None:
    settings = TEST_SETTINGS.model_copy(
        update={
            "agent_context_window_tokens": 100_000,
            "agent_context_window_ratio": 0.8,
            "agent_compact_keep_messages": 4,
        }
    )
    wide = ModelInfo("test", "vendor/wide", context_window=262_144)

    assert context_budget(settings, wide) == ContextBudget(262_144, 0.8, 4)
    assert context_budget(settings, ModelInfo("test", "vendor/unknown")).window_tokens == 100_000
    assert context_budget(settings, None).window_tokens == 100_000


def test_the_guard_summarizes_at_the_budgets_share_of_the_window() -> None:
    model = FakeMessagesListChatModel(responses=[AIMessage(content="")])

    (guard,) = context_guard(model, BUDGET)

    assert isinstance(guard, SummarizationMiddleware)
    assert (guard.trigger, guard.keep) == (("tokens", 1_000), ("messages", 2))
    assert guard.model is model
    assert context_guard(model, None) == []


@pytest.mark.asyncio
async def test_a_step_agents_long_loop_is_compacted_by_its_own_model() -> None:
    toolset = AgentToolset(MCPConnections(), [read_everything])
    task = AgentTask("Read it all", "m", "Reader", ["read_everything"])

    guarded = LangGraphStepAgent(reading_model(), toolset, AgentLimits(5, 9, 1, BUDGET))
    unguarded = LangGraphStepAgent(reading_model(), toolset, AgentLimits(5, 9, 1), StepServices())

    # The guard spends the model's second answer on the summary; the third is the reply.
    assert (await guarded.reply(task)).output == "Done: 20,000 characters read."
    assert (await unguarded.reply(task)).output == "Notes on what was read."


@pytest.mark.asyncio
async def test_the_chat_agent_gets_the_same_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeGraph:
        async def astream(self, state: object, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            yield {"type": "other", "data": None}

    def fake_create_agent(model: object, tools: object, **kwargs: object) -> FakeGraph:
        captured["middleware"] = kwargs["middleware"]
        return FakeGraph()

    async def fake_discover(configured: object, native: list[Any], timeout: float) -> list[Any]:
        return native

    monkeypatch.setattr(agent_runtime, "discover_tools", fake_discover)
    monkeypatch.setattr(agent_service, "create_agent", fake_create_agent)
    model = FakeMessagesListChatModel(responses=[AIMessage(content="hi")])
    agent = LangGraphChatAgent(model, AgentToolset({}, []), AgentLimits(10, 9, 1, BUDGET))  # type: ignore[arg-type]

    [event async for event in agent.stream(Conversation("hello"))]

    guards = [m for m in captured["middleware"] if isinstance(m, SummarizationMiddleware)]
    assert len(guards) == 1
    assert (guards[0].trigger, guards[0].model) == (("tokens", 1_000), model)
