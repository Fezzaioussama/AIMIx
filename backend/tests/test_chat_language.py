"""The chat answers in the person's language: after a tool's result, which may be in
another one, the model's next call is reminded of the rule and of how the person's
message began."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool, tool

from api.services.agent import LangGraphChatAgent
from api.services.agent_runtime import AgentLimits, AgentToolset
from api.services.chat_conversation import Conversation
from api.services.chat_prompts import (
    CHAT_LANGUAGE_RULE,
    LANGUAGE_REMINDER_QUOTE_CHARS,
    language_reminder,
)
from api.services.mcp import MCPConnections

PROMPT = "What did my last run say?"
REMINDER = language_reminder(PROMPT)


class ModelInputs(BaseCallbackHandler):
    """The messages of every model call, in order."""

    def __init__(self) -> None:
        self.calls: list[list[BaseMessage]] = []

    def on_chat_model_start(
        self, serialized: dict[str, Any], messages: list[list[BaseMessage]], **kwargs: Any
    ) -> None:
        self.calls.extend(messages)


def calling(name: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": {}, "id": f"call-{name}"}])


async def model_inputs(
    monkeypatch: pytest.MonkeyPatch, tools: list[BaseTool], replies: list[AIMessage]
) -> list[list[BaseMessage]]:
    monkeypatch.setattr(
        FakeMessagesListChatModel, "bind_tools", lambda self, tools, **kwargs: self, raising=False
    )
    inputs = ModelInputs()
    model = FakeMessagesListChatModel(responses=replies, callbacks=[inputs])
    agent = LangGraphChatAgent(model, AgentToolset(MCPConnections(), tools), AgentLimits(10, 9, 1))
    _ = [event async for event in agent.stream(Conversation(PROMPT))]
    return inputs.calls


@tool
def latest_run() -> str:
    """The person's latest run."""
    return "Voici le résumé de la semaine."


@tool
def run_details() -> str:
    """One run's details."""
    return "Les détails, en français."


@tool
def in_blocks() -> list[dict[str, str]]:
    """A result in content blocks, as MCP tools give theirs."""
    return [{"type": "text", "text": "Résultat"}]


def test_the_reminder_repeats_the_rule_and_quotes_how_the_message_began() -> None:
    reminder = language_reminder("  Résume   ma\n dernière exécution " + "x" * 200)

    assert reminder.startswith(CHAT_LANGUAGE_RULE)
    quoted = reminder.split('began: "')[1].removesuffix('"')
    assert quoted.startswith("Résume ma dernière exécution x")
    assert len(quoted) == LANGUAGE_REMINDER_QUOTE_CHARS


@pytest.mark.asyncio
async def test_each_call_after_a_tool_result_is_reminded_and_the_result_stays_as_it_was(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replies = [calling("latest_run"), calling("run_details"), AIMessage(content="Here it is.")]

    first, second, third = await model_inputs(monkeypatch, [latest_run, run_details], replies)

    assert isinstance(first[-1], HumanMessage)
    assert not any(REMINDER in str(message.content) for message in first)
    assert second[-1].content == f"Voici le résumé de la semaine.\n\n{REMINDER}"
    # Only the newest result carries it: the conversation keeps each tool's own words.
    assert [message.content for message in third if isinstance(message, ToolMessage)] == [
        "Voici le résumé de la semaine.",
        f"Les détails, en français.\n\n{REMINDER}",
    ]


@pytest.mark.asyncio
async def test_a_result_in_content_blocks_gets_the_reminder_as_its_last_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replies = [calling("in_blocks"), AIMessage(content="Done.")]

    _, after = await model_inputs(monkeypatch, [in_blocks], replies)

    assert after[-1].content == [
        {"type": "text", "text": "Résultat"},
        {"type": "text", "text": REMINDER},
    ]
