"""Request-scoped LangGraph chat agent with configured MCP tools."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from time import monotonic

import anyio
import httpx
import openai
from exceptiongroup import ExceptionGroup
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import Connection
from langgraph.errors import GraphRecursionError
from mcp import McpError
from openrouter.errors import NoResponseError, OpenRouterError

from api.db import Database
from api.exceptions import (
    DomainError,
    ProviderTimedOut,
    ProviderUnavailable,
    ToolUnavailable,
    UpstreamResponseInvalid,
)
from api.models import User
from api.services.agent_tools import built_in_tools
from api.services.llm import get_agent_model
from api.services.mcp import connections
from api.services.pipelines import StepGenerator
from config.settings import get_settings

logger = logging.getLogger(__name__)

AGENT_FAILURES = (
    TimeoutError,
    httpx.TimeoutException,
    openai.APITimeoutError,
    McpError,
    ExceptionGroup,
    httpx.HTTPError,
    openai.APIError,
    OpenRouterError,
    NoResponseError,
    GraphRecursionError,
)


def _as_domain_error(cause: Exception) -> DomainError:
    if isinstance(cause, (TimeoutError, httpx.TimeoutException, openai.APITimeoutError)):
        return ProviderTimedOut("The agent timed out.")
    if isinstance(cause, (McpError, ExceptionGroup)):
        return ToolUnavailable("An MCP server or tool is unavailable.")
    return ProviderUnavailable("The agent could not complete the request.")


@dataclass(frozen=True)
class AgentLimits:
    timeout_seconds: float
    recursion_limit: int


@dataclass(frozen=True)
class AgentToolset:
    mcp_connections: dict[str, Connection]
    native_tools: list[BaseTool]


class LangGraphChatAgent:
    def __init__(self, model: BaseChatModel, toolset: AgentToolset, limits: AgentLimits) -> None:
        self._model = model
        self._toolset = toolset
        self._limits = limits

    async def _load_tools(self) -> list[BaseTool]:
        client = MultiServerMCPClient(self._toolset.mcp_connections, tool_name_prefix=True)
        try:
            mcp_tools = await client.get_tools()
        except (McpError, ExceptionGroup, httpx.HTTPError) as cause:
            logger.warning("chat.mcp_discovery_failed error=%s", type(cause).__name__)
            raise ToolUnavailable("An MCP server is unavailable.") from cause
        return [*self._toolset.native_tools, *mcp_tools]

    async def _execute(self, prompt: str, queue: asyncio.Queue[str | None]) -> None:
        started = monotonic()
        with anyio.fail_after(self._limits.timeout_seconds):
            tools = await self._load_tools()
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
            raise _as_domain_error(cause) from cause
        finally:
            queue.put_nowait(None)

    async def reply(self, prompt: str) -> str:
        """Return only the final assistant message after all tool calls."""
        started = monotonic()
        try:
            with anyio.fail_after(self._limits.timeout_seconds):
                tools = await self._load_tools()
                graph = create_agent(self._model, tools)
                state = await graph.ainvoke(
                    {"messages": [{"role": "user", "content": prompt}]},
                    config={"recursion_limit": self._limits.recursion_limit},
                )
        except AGENT_FAILURES as cause:
            logger.warning("pipeline.agent_failed error=%s", type(cause).__name__)
            raise _as_domain_error(cause) from cause
        messages = state.get("messages", [])
        message = messages[-1] if messages else None
        if not isinstance(message, AIMessage) or not message.text.strip():
            raise UpstreamResponseInvalid("The pipeline agent returned no text.")
        logger.info(
            "pipeline.agent_completed tools=%d duration_ms=%.1f",
            len(tools),
            (monotonic() - started) * 1000,
        )
        return message.text

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
    database: Database, user: User, generator_factory: Callable[[], StepGenerator]
) -> LangGraphChatAgent:
    settings = get_settings()
    return LangGraphChatAgent(
        get_agent_model(),
        AgentToolset(
            connections(settings.mcp_servers, settings.mcp_timeout_seconds),
            built_in_tools(database, user, generator_factory),
        ),
        AgentLimits(settings.agent_timeout_seconds, settings.agent_recursion_limit),
    )
