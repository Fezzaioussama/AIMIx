"""Shared tool policy, limits and failure contract for chat and pipeline agents,
and the context guard that keeps an agent's tool loop inside its model's window."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import openai
from exceptiongroup import ExceptionGroup
from langchain.agents.middleware import AgentMiddleware, SummarizationMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool, ToolException
from langgraph.errors import GraphRecursionError
from mcp import McpError
from openrouter.errors import NoResponseError, OpenRouterError

from api.exceptions import DomainError, ProviderTimedOut, ProviderUnavailable, ToolUnavailable
from api.services.approvals.policy import NO_APPROVALS, ApprovalPolicy
from api.services.mcp import MCPConnections
from api.services.mcp_discovery import discover_tools
from config.settings import Settings
from llm.catalog import ModelInfo

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
    ToolException,
)


@dataclass(frozen=True)
class ContextBudget:
    """How full a model's context window an agent's messages may get before the
    oldest are summarized, and how many of the newest stay verbatim (§7 Value Object)."""

    #: The window the guard works against: the model's own, else the configured default.
    window_tokens: int
    ratio: float
    keep_messages: int


@dataclass(frozen=True)
class AgentLimits:
    timeout_seconds: float
    recursion_limit: int
    mcp_timeout_seconds: float
    #: The context guard's budget; None leaves an agent's messages unbounded.
    context: ContextBudget | None = None


def context_budget(settings: Settings, info: ModelInfo | None) -> ContextBudget:
    """The budget for one model: its catalogue window when known, else the default."""
    known = info.context_window if info is not None else None
    return ContextBudget(
        known or settings.agent_context_window_tokens,
        settings.agent_context_window_ratio,
        settings.agent_compact_keep_messages,
    )


def context_guard(
    model: BaseChatModel, budget: ContextBudget | None
) -> list[AgentMiddleware[Any, Any, Any]]:
    """The middleware that keeps an agent's tool loop inside its model's context
    window (after Celia Agent's proactive compaction): before a model call, once the
    messages are estimated at ``ratio`` of the window, ``model`` summarizes the older
    ones and the newest ``keep_messages`` stay verbatim. Nothing without a budget."""
    if budget is None:
        return []
    guard = SummarizationMiddleware(
        model,
        trigger=("tokens", int(budget.window_tokens * budget.ratio)),
        keep=("messages", budget.keep_messages),
    )
    return [guard]


@dataclass(frozen=True)
class AgentToolset:
    mcp_connections: MCPConnections
    native_tools: list[BaseTool]
    #: Which of these tools must ask the run's owner first (``approvals.guard``).
    approvals: ApprovalPolicy = NO_APPROVALS


def as_agent_error(cause: Exception) -> DomainError:
    """Translate third-party failures to the application's error contract."""
    if isinstance(cause, (TimeoutError, httpx.TimeoutException, openai.APITimeoutError)):
        return ProviderTimedOut("The agent timed out.")
    if isinstance(cause, (McpError, ExceptionGroup, ToolException)):
        return ToolUnavailable("An MCP server or tool is unavailable.")
    return ProviderUnavailable("The agent could not complete the request.")


async def resolve_tools(
    toolset: AgentToolset, allowed: list[str] | None, timeout_seconds: float
) -> list[BaseTool]:
    """Apply one tool policy to native and configured MCP tools."""
    if allowed == []:
        return []
    native = toolset.native_tools
    if allowed is not None and set(allowed) <= {item.name for item in native}:
        return [item for item in native if item.name in allowed]
    tools = await discover_tools(toolset.mcp_connections, native, timeout_seconds)
    if allowed is None:
        return tools
    selected = [item for item in tools if item.name in allowed]
    # A tool of an integration that could not be reached is missing here too.
    if missing := sorted(set(allowed) - {item.name for item in selected}):
        raise ToolUnavailable(f"A selected agent tool is unavailable: {', '.join(missing)}.")
    return selected
