"""LangGraph adapter for one configured step in a multiagent pipeline."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic

import anyio
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from api.db import Database
from api.exceptions import UpstreamResponseInvalid
from api.models import User
from api.services.agent_runtime import (
    AGENT_FAILURES,
    AgentLimits,
    AgentToolset,
    as_agent_error,
    resolve_tools,
)
from api.services.agent_tools import read_only_tools
from api.services.agent_types import AgentOutcome, AgentTask, ToolCallTrace
from api.services.llm import get_agent_model
from api.services.mcp import connections
from config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StepAgentDependencies:
    """Replace the model factory or runtime settings without changing graph code."""

    model_factory: Callable[[str], BaseChatModel]
    settings: Settings


def _tool_trace(messages: list[BaseMessage]) -> list[ToolCallTrace]:
    """Record tool names and statuses without retaining inputs or outputs."""
    names: dict[str, str] = {}
    calls: list[ToolCallTrace] = []
    for message in messages:
        if isinstance(message, AIMessage):
            names.update(
                {str(call["id"]): call["name"] for call in message.tool_calls if call.get("id")}
            )
        elif isinstance(message, ToolMessage):
            name = names.get(message.tool_call_id, message.name or "unknown")
            calls.append(ToolCallTrace(name=name, status=message.status))
    return calls


class LangGraphStepAgent:
    """Run one role-scoped agent with its selected model and tools."""

    def __init__(self, model: BaseChatModel, toolset: AgentToolset, limits: AgentLimits) -> None:
        self._model = model
        self._toolset = toolset
        self._limits = limits

    async def reply(self, task: AgentTask) -> AgentOutcome:
        started = monotonic()
        try:
            with anyio.fail_after(self._limits.timeout_seconds):
                tools = await resolve_tools(
                    self._toolset, task.allowed_tools, self._limits.mcp_timeout_seconds
                )
                system_prompt = (
                    f"You are the {task.role} agent in an AIMIx pipeline." if task.role else None
                )
                graph = create_agent(self._model, tools, system_prompt=system_prompt)
                state = await graph.ainvoke(
                    {"messages": [{"role": "user", "content": task.prompt}]},
                    config={"recursion_limit": self._limits.recursion_limit},
                )
        except AGENT_FAILURES as cause:
            logger.warning("pipeline.agent_failed error=%s", type(cause).__name__)
            raise as_agent_error(cause) from cause
        messages = state.get("messages", [])
        message = messages[-1] if messages else None
        if not isinstance(message, AIMessage) or not message.text.strip():
            raise UpstreamResponseInvalid("The pipeline agent returned no text.")
        logger.info(
            "pipeline.agent_completed tools=%d duration_ms=%.1f",
            len(tools),
            (monotonic() - started) * 1000,
        )
        return AgentOutcome(message.text, _tool_trace(messages))


class PipelineAgentGenerator:
    """Bind the step-agent adapter to one user and configured model factory."""

    def __init__(
        self,
        database: Database,
        user: User,
        dependencies: StepAgentDependencies | None = None,
    ) -> None:
        self._database = database
        self._user = user
        self._dependencies = dependencies or StepAgentDependencies(get_agent_model, get_settings())

    async def execute(self, task: AgentTask) -> AgentOutcome:
        settings = self._dependencies.settings
        agent = LangGraphStepAgent(
            self._dependencies.model_factory(task.model),
            AgentToolset(
                connections(settings.mcp_servers, settings.mcp_timeout_seconds),
                read_only_tools(self._database, self._user),
            ),
            AgentLimits(
                settings.agent_timeout_seconds,
                settings.agent_recursion_limit,
                settings.mcp_timeout_seconds,
            ),
        )
        return await agent.reply(task)
