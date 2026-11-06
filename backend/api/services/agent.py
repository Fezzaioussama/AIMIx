"""Request-scoped LangGraph chat agent with configured MCP tools.

Its model is metered like a pipeline step's (``llm.usage``): every call behind
one chat message counts toward that message's token limit (CHAT_MAX_TOKENS),
and a call past it is refused with ``BudgetExceeded``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from time import monotonic
from typing import Any
from uuid import UUID

import anyio
from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallRequest, wrap_tool_call
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool, ToolException

from api.exceptions import BudgetExceeded
from api.models import UsageKind
from api.services.account_usage import account_meter, calls_of
from api.services.agent_runtime import (
    AGENT_FAILURES,
    AgentLimits,
    AgentToolset,
    as_agent_error,
    resolve_tools,
)
from api.services.agent_tools import built_in_tools
from api.services.approvals.guard import guard_tools
from api.services.approvals.policy import approval_policy_for
from api.services.chat_conversation import Conversation, model_messages
from api.services.chat_events import (
    ChatEvent,
    text_event,
    tool_failed,
    tool_finished,
    tool_started,
)
from api.services.chat_language import answer_in_their_language
from api.services.chat_prompts import chat_system_prompt
from api.services.chat_tools.deliveries import delivery_tools
from api.services.chat_tools.runs import run_tools
from api.services.chat_tools.scope import ChatScope
from api.services.chat_tools.settings import settings_tools
from api.services.chat_tools.templates import template_tools
from api.services.chat_tools.webhooks import webhook_tools
from api.services.chat_tools.workflows import workflow_tools
from api.services.integrations.connections import mcp_connections_for
from api.services.llm import LLMProfile, get_agent_model, model_info
from api.services.run_budget import RunBudget, limit_reached
from api.services.run_recorder import utcnow
from api.services.runs import launcher
from config.settings import get_settings
from llm.usage import NO_USAGE, UNMETERED, TokenUsage, UsageCallback, UsageMeter, chained, metered

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


def metered_chat_model(
    profile: LLMProfile, max_tokens: int | None, account: UsageMeter = UNMETERED
) -> BaseChatModel:
    """The profile's chat model, every call of which counts toward one message's
    ``max_tokens`` (None: counted, never refused) and, through ``account``, the
    account's day (``account_usage``)."""
    message = ChatMeter(RunBudget(max_tokens=max_tokens))
    usage = UsageCallback(model_info(profile, profile.default_model), chained(message, account))
    return metered(get_agent_model(profile), usage)


@wrap_tool_call
async def refusals_as_results(
    request: ToolCallRequest, handler: Callable[[ToolCallRequest], Awaitable[Any]]
) -> Any:
    """A refused write reaches the model as an error result, not as a dead chat.

    LangGraph's ToolNode re-raises a plain ``ToolException``, which would end the
    reply; this middleware turns it into the error message the model explains.
    """
    try:
        return await handler(request)
    except ToolException as cause:
        return ToolMessage(
            content=f"The tool refused: {cause}",
            name=str(request.tool_call["name"]),
            tool_call_id=str(request.tool_call["id"]),
            status="error",
        )


class _ToolEvents(BaseCallbackHandler):
    """Turns a tool's start, end and failure into chat events for the screen."""

    def __init__(
        self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue[ChatEvent | None]
    ) -> None:
        self._loop = loop
        self._queue = queue
        self._names: dict[UUID, str] = {}
        self._lock = threading.Lock()

    def _emit(self, event: ChatEvent) -> None:
        # Tools may run in a worker thread; the queue belongs to the event loop.
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)

    def _take(self, run_id: UUID) -> str | None:
        with self._lock:
            return self._names.pop(run_id, None)

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        name = serialized.get("name")
        if not isinstance(name, str):
            return
        with self._lock:
            self._names[run_id] = name
        self._emit(tool_started(name))

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        if name := self._take(run_id):
            self._emit(tool_finished(name, output))

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        if name := self._take(run_id):
            self._emit(tool_failed(name, str(error)[:300]))


class _Paragraphs:
    """Starts the text of a new model reply (after a tool call) on a new paragraph, so
    two replies' sentences never run together on the screen."""

    def __init__(self) -> None:
        self._last: str | None = None

    def text(self, message: AIMessage) -> str:
        separate = self._last is not None and message.id != self._last
        self._last = message.id
        return f"\n\n{message.text}" if separate else message.text


class LangGraphChatAgent:
    def __init__(self, model: BaseChatModel, toolset: AgentToolset, limits: AgentLimits) -> None:
        self._model = model
        self._toolset = toolset
        self._limits = limits

    async def _execute(
        self, conversation: Conversation, queue: asyncio.Queue[ChatEvent | None]
    ) -> None:
        started = monotonic()
        with anyio.fail_after(self._limits.timeout_seconds):
            resolved = await resolve_tools(self._toolset, None, self._limits.mcp_timeout_seconds)
            # A chat has no run to pause: the tools that must ask first are left out.
            tools = guard_tools(self._toolset, resolved, None).tools
            graph = create_agent(
                self._model,
                tools,
                system_prompt=chat_system_prompt(utcnow(), conversation.timezone),
                middleware=[refusals_as_results, answer_in_their_language(conversation.prompt)],
            )
            events = graph.astream(
                # A list display, so it takes the graph's message type.
                {"messages": [*model_messages(conversation)]},
                stream_mode="messages",
                version="v2",
                config={
                    "recursion_limit": self._limits.recursion_limit,
                    "callbacks": [_ToolEvents(asyncio.get_running_loop(), queue)],
                },
            )
            paragraphs = _Paragraphs()
            async for event in events:
                if event["type"] != "messages":
                    continue
                message, metadata = event["data"]
                if (
                    metadata.get("langgraph_node") == "model"
                    and isinstance(message, AIMessage)
                    and message.text
                ):
                    queue.put_nowait(text_event(paragraphs.text(message)))
        logger.info(
            "chat.agent_completed tools=%d duration_ms=%.1f",
            len(tools),
            (monotonic() - started) * 1000,
        )

    async def _produce(
        self, conversation: Conversation, queue: asyncio.Queue[ChatEvent | None]
    ) -> None:
        try:
            await self._execute(conversation, queue)
        except AGENT_FAILURES as cause:
            logger.warning("chat.agent_failed error=%s", type(cause).__name__)
            raise as_agent_error(cause) from cause
        finally:
            queue.put_nowait(None)

    async def stream(self, conversation: Conversation) -> AsyncIterator[ChatEvent]:
        queue: asyncio.Queue[ChatEvent | None] = asyncio.Queue()
        producer = asyncio.create_task(self._produce(conversation, queue))
        try:
            while (event := await queue.get()) is not None:
                yield event
            await producer
        finally:
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)


def chat_tools(scope: ChatScope) -> list[BaseTool]:
    """Every native tool of the chat: pipelines, runs and schedules (``agent_tools``),
    then one module per area of ``chat_tools``: the planner's design and change
    tools, runs, templates, settings, webhooks and result deliveries."""
    launch = launcher(scope.runs, scope.user, scope.agents)
    return [
        *built_in_tools(scope.database, scope.user, launch, scope.schedules),
        *workflow_tools(scope),
        *run_tools(scope),
        *template_tools(scope),
        *settings_tools(scope),
        *webhook_tools(scope),
        *delivery_tools(scope),
    ]


def get_chat_agent(scope: ChatScope) -> LangGraphChatAgent:
    settings = get_settings()
    calls = calls_of(UsageKind.CHAT, scope.profile.default_model)
    account = account_meter(scope.database, scope.user.id, scope.profile, calls)
    return LangGraphChatAgent(
        metered_chat_model(scope.profile, settings.chat_max_tokens, account),
        AgentToolset(
            mcp_connections_for(scope.database, scope.user, settings),
            chat_tools(scope),
            approval_policy_for(scope.database, scope.user, settings),
        ),
        AgentLimits(
            settings.agent_timeout_seconds,
            settings.agent_recursion_limit,
            settings.mcp_timeout_seconds,
        ),
    )
