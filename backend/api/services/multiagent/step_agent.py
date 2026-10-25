"""LangGraph adapter for one configured step in a multiagent pipeline."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
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
from api.services.agent_tools import native_tools
from api.services.agent_types import AgentOutcome, AgentTask, ToolCallTrace
from api.services.approvals.gate import ApprovalGate
from api.services.approvals.guard import guard_tools, run_gate
from api.services.approvals.policy import approval_policy_for
from api.services.integrations.connections import mcp_connections_for
from api.services.llm import LLMProfile, get_agent_model, model_info
from api.services.prompts import step_agent_system_prompt
from config.settings import Settings, get_settings
from llm.catalog import ModelInfo
from llm.usage import UsageCallback, metered

logger = logging.getLogger(__name__)


def _unlisted(model_id: str) -> ModelInfo | None:
    return None


@dataclass(frozen=True)
class StepAgentDependencies:
    """Replace the model factory or runtime settings without changing graph code."""

    model_factory: Callable[[str], BaseChatModel]
    settings: Settings
    #: A model's catalogue entry, whose prices price its calls when the
    #: provider reports no cost; by default no model has one.
    model_info: Callable[[str], ModelInfo | None] = _unlisted


@dataclass(frozen=True)
class StepServices:
    """What a step agent calls besides its model and tools: the catalogue entry
    that prices its calls (``info``), and the gate that asks the run's owner
    before a tool acts (``gate``). Either may be missing: an unpriced call has
    no cost, and tools that must ask are left out when nobody can be asked."""

    info: ModelInfo | None = None
    gate: ApprovalGate | None = None


NO_SERVICES = StepServices()


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

    def __init__(
        self,
        model: BaseChatModel,
        toolset: AgentToolset,
        limits: AgentLimits,
        services: StepServices = NO_SERVICES,
    ) -> None:
        """``services.gate`` holds the tools that must ask the run's owner first;
        without one those tools are not offered."""
        self._model = model
        self._toolset = toolset
        self._limits = limits
        self._info = services.info
        self._gate = services.gate

    async def reply(self, task: AgentTask) -> AgentOutcome:
        started = monotonic()
        # Counts every model call of this step, and lets the task's meter refuse one.
        usage = UsageCallback(self._info, task.meter)
        try:
            with anyio.fail_after(self._limits.timeout_seconds):
                resolved = await resolve_tools(
                    self._toolset, task.allowed_tools, self._limits.mcp_timeout_seconds
                )
                guarded = guard_tools(self._toolset, resolved, self._gate)
                tools = guarded.tools
                system_prompt = step_agent_system_prompt(
                    task.role,
                    has_tools=bool(tools),
                    expected_output=task.expected_output,
                    reviewer=task.reviewer,
                )
                model = metered(self._model, usage)
                graph = create_agent(
                    model, tools, system_prompt=system_prompt, middleware=guarded.middleware
                )
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
        return AgentOutcome(message.text, _tool_trace(messages), usage.total)


class PipelineAgentGenerator:
    """Bind the step-agent adapter to one user, their LLM profile and a model factory."""

    def __init__(
        self,
        database: Database,
        user: User,
        profile: LLMProfile,
        dependencies: StepAgentDependencies | None = None,
    ) -> None:
        self._database = database
        self._user = user
        self._dependencies = dependencies or StepAgentDependencies(
            partial(get_agent_model, profile), get_settings(), partial(model_info, profile)
        )

    async def execute(self, task: AgentTask) -> AgentOutcome:
        settings = self._dependencies.settings
        agent = LangGraphStepAgent(
            self._dependencies.model_factory(task.model),
            AgentToolset(
                mcp_connections_for(self._database, self._user, settings),
                native_tools(self._database, self._user, settings),
                approval_policy_for(self._database, self._user, settings),
            ),
            AgentLimits(
                settings.agent_timeout_seconds,
                settings.agent_recursion_limit,
                settings.mcp_timeout_seconds,
            ),
            StepServices(
                self._dependencies.model_info(task.model),
                run_gate(self._database, task.run_step, settings),
            ),
        )
        return await agent.reply(task)
