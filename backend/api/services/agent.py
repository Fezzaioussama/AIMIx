"""Request-scoped LangGraph chat agent with configured MCP tools.

Its model is metered like a pipeline step's (``llm.usage``): every call behind
one chat message counts toward that message's token limit (CHAT_MAX_TOKENS),
and a call past it is refused with ``BudgetExceeded``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterator
from time import monotonic

import anyio
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage

from api.db import Database
from api.exceptions import BudgetExceeded
from api.models import User
from api.services.agent_runtime import (
    AGENT_FAILURES,
    AgentLimits,
    AgentToolset,
    as_agent_error,
    resolve_tools,
)
from api.services.agent_tools import PipelineLauncher, built_in_tools
from api.services.approvals.guard import guard_tools
from api.services.approvals.policy import approval_policy_for
from api.services.integrations.connections import mcp_connections_for
from api.services.llm import LLMProfile, get_agent_model, model_info
from api.services.run_budget import RunBudget, limit_reached
from config.settings import get_settings
from llm.usage import NO_USAGE, TokenUsage, UsageCallback, metered

logger = logging.getLogger(__name__)


class ChatMeter:
    """What the model calls behind one chat message used; refuses the next call
    once they reach the message's limit (a ``UsageMeter``)."""

    def __init__(self, budget: RunBudget) -> None:
        self._budget = budget
        self._lock = threading.Lock()
        self._spent = NO_USAGE

    def before_call(self) -> None:
        with self._lock:
            reached = limit_reached(self._budget, self._spent)
        if reached is not None:
            raise BudgetExceeded(
                f"This reply stopped at {reached.used} because it reached "
                f"its {reached.limit} limit."
            )

    def after_call(self, usage: TokenUsage) -> None:
        with self._lock:
            self._spent += usage


def metered_chat_model(profile: LLMProfile, max_tokens: int | None) -> BaseChatModel:
    """The profile's chat model, every call of which counts toward one message's
    ``max_tokens`` (None: counted, never refused)."""
    usage = UsageCallback(
        model_info(profile, profile.default_model), ChatMeter(RunBudget(max_tokens=max_tokens))
    )
    return metered(get_agent_model(profile), usage)


class LangGraphChatAgent:
    def __init__(self, model: BaseChatModel, toolset: AgentToolset, limits: AgentLimits) -> None:
        self._model = model
        self._toolset = toolset
        self._limits = limits

    async def _execute(self, prompt: str, queue: asyncio.Queue[str | None]) -> None:
        started = monotonic()
        with anyio.fail_after(self._limits.timeout_seconds):
            resolved = await resolve_tools(self._toolset, None, self._limits.mcp_timeout_seconds)
            # A chat has no run to pause: the tools that must ask first are left out.
            tools = guard_tools(self._toolset, resolved, None).tools
            graph = create_agent(self._model, tools)
            events = graph.astream(
                {"messages": [{"role": "user", "content": prompt}]},
                stream_mode="messages",
                version="v2",
                config={"recursion_limit": self._limits.recursion_limit},
            )
            async for event in events:
                if event["type"] != "messages":
                    continue
                message, metadata = event["data"]
                if (
                    metadata.get("langgraph_node") == "model"
                    and isinstance(message, AIMessage)
                    and (text := message.text)
                ):
                    queue.put_nowait(text)
        logger.info(
            "chat.agent_completed tools=%d duration_ms=%.1f",
            len(tools),
            (monotonic() - started) * 1000,
        )

    async def _produce(self, prompt: str, queue: asyncio.Queue[str | None]) -> None:
        try:
            await self._execute(prompt, queue)
        except AGENT_FAILURES as cause:
            logger.warning("chat.agent_failed error=%s", type(cause).__name__)
            raise as_agent_error(cause) from cause
        finally:
            queue.put_nowait(None)

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        producer = asyncio.create_task(self._produce(prompt, queue))
        try:
            while (chunk := await queue.get()) is not None:
                yield chunk
            await producer
        finally:
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)


def get_chat_agent(
    database: Database,
    user: User,
    profile: LLMProfile,
    launch: PipelineLauncher,
) -> LangGraphChatAgent:
    settings = get_settings()
    return LangGraphChatAgent(
        metered_chat_model(profile, settings.chat_max_tokens),
        AgentToolset(
            mcp_connections_for(database, user, settings),
            built_in_tools(database, user, launch),
            approval_policy_for(database, user, settings),
        ),
        AgentLimits(
            settings.agent_timeout_seconds,
            settings.agent_recursion_limit,
            settings.mcp_timeout_seconds,
        ),
    )
