"""LangGraph adapter for one configured step in a multiagent pipeline."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from functools import partial
from time import monotonic

import anyio
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from api.db import Database
from api.exceptions import UpstreamResponseInvalid
from api.models import User
from api.repositories import runs as run_repository
from api.services import user_memory
from api.services.agent_prompts import AgentRole, step_agent_system_prompt
from api.services.agent_runtime import (
    AGENT_FAILURES,
    AgentLimits,
    AgentToolset,
    as_agent_error,
    context_budget,
    context_guard,
    resolve_tools,
)
from api.services.agent_tools import native_tools
from api.services.agent_types import AgentOutcome, AgentTask, RunStepRef, ToolCallTrace
from api.services.approvals.gate import ApprovalGate
from api.services.approvals.guard import guard_tools, run_gate
from api.services.approvals.policy import approval_policy_for
from api.services.integrations.connections import mcp_connections_for
from api.services.llm import LLMProfile, get_agent_model, model_info
from config.settings import Settings, get_settings
from llm.catalog import ModelInfo
from llm.usage import UsageCallback, metered

logger = logging.getLogger(__name__)

#: A model's own control token in its reply (``<|endoftext|>``, ``<|im_end|>``): the
#: mark of a reply that went off the rails, which must never pass for a deliverable.
CONTROL_TOKEN = re.compile(r"<\|[a-z_]{2,40}\|>")


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
    that prices its calls (``info``), the gate that asks the run's owner before a
    tool acts (``gate``), and what the owner told AIMIx to keep in mind
    (``instructions``, Settings → Memory). Each may be missing: an unpriced call
    has no cost, tools that must ask are left out when nobody can be asked, and
    an owner who wrote nothing adds nothing to the prompt."""

    info: ModelInfo | None = None
    gate: ApprovalGate | None = None
    instructions: str = ""


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
        self._instructions = services.instructions

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
                role = AgentRole(
                    task.role, task.expected_output, task.reviewer, task.context, self._instructions
                )
                system_prompt = step_agent_system_prompt(role, [tool.name for tool in tools])
                model = metered(self._model, usage)
                # The guard summarizes with the metered model: that call is counted too.
                middleware = [*guarded.middleware, *context_guard(model, self._limits.context)]
                graph = create_agent(
                    model, tools, system_prompt=system_prompt, middleware=middleware
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
        if CONTROL_TOKEN.search(message.text):
            raise UpstreamResponseInvalid("The pipeline agent returned garbled text.")
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
        self._default_model = profile.default_model
        self._dependencies = dependencies or StepAgentDependencies(
            partial(get_agent_model, profile), get_settings(), partial(model_info, profile)
        )
        #: What the owner told AIMIx to keep in mind, read once, at the first step.
        self._instructions: str | None = None

    async def execute(self, task: AgentTask) -> AgentOutcome:
        """Run the step; a reply with no text or garbled text gets one more try before the
        step fails, on the default model (which often answers when another model failed),
        or, when that model is the one that failed, without tools (which some models trip
        over). The meter counts both tries."""
        try:
            return await self._reply(task)
        except UpstreamResponseInvalid:
            retry = replace(task, model=self._default_model or task.model)
            if retry.model == task.model and task.allowed_tools != []:
                retry = replace(retry, allowed_tools=[])
            logger.warning(
                "pipeline.agent_retry model=%s retry_model=%s without_tools=%s",
                task.model,
                retry.model,
                retry.allowed_tools == [] and task.allowed_tools != [],
            )
            return await self._reply(retry)

    async def _reply(self, task: AgentTask) -> AgentOutcome:
        settings = self._dependencies.settings
        info = self._dependencies.model_info(task.model)
        agent = LangGraphStepAgent(
            self._dependencies.model_factory(task.model),
            AgentToolset(
                mcp_connections_for(self._database, self._user, settings),
                native_tools(
                    self._database,
                    self._user,
                    settings,
                    _drafts_since(self._database, task.run_step),
                ),
                approval_policy_for(self._database, self._user, settings),
            ),
            AgentLimits(
                settings.agent_timeout_seconds,
                settings.agent_recursion_limit,
                settings.mcp_timeout_seconds,
                context_budget(settings, info),
            ),
            StepServices(
                info, run_gate(self._database, task.run_step, settings), self._remembered()
            ),
        )
        return await agent.reply(task)

    def _remembered(self) -> str:
        if self._instructions is None:
            with self._database.session() as session:
                self._instructions = user_memory.instructions_for(session, self._user)
        return self._instructions


def _drafts_since(database: Database, step: RunStepRef | None) -> datetime | None:
    """When the step's run started: its agents may replace the files saved since then,
    their own drafts. None outside a recorded run, where nothing is replaced."""
    if step is None:
        return None
    with database.session() as session:
        run = run_repository.load(session, step.run_id)
    started = run.started_at if run else None
    # SQLite hands back the UTC time it stored without its zone.
    return started.replace(tzinfo=timezone.utc) if started and started.tzinfo is None else started
