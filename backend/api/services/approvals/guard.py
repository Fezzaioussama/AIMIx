"""Hands an agent its tools, with the approval gate in front of those that ask.

The one place that applies ``ApprovalPolicy`` to an agent's tools, for the
chat agent and pipeline step agents alike: a step of a recorded run keeps
every tool and its gated ones wait for the owner; where nobody can be asked
(the chat, a step outside a recorded run) the tools that ask are not offered.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import BaseTool

from api.db import Database
from api.services.agent_runtime import AgentToolset
from api.services.agent_types import RunStepRef
from api.services.approvals.gate import ApprovalGate, RunApprovalGate, approval_limits
from api.services.approvals.middleware import ApprovalMiddleware
from api.services.tool_catalog import source_of
from config.settings import Settings


@dataclass(frozen=True)
class GuardedTools:
    """What an agent is built with: its tools, and the middleware that gates some."""

    tools: list[BaseTool]
    middleware: list[AgentMiddleware] = field(default_factory=list)


def guard_tools(
    toolset: AgentToolset, tools: list[BaseTool], gate: ApprovalGate | None
) -> GuardedTools:
    """``tools`` (resolved from ``toolset``) with those that ask first behind
    ``gate``; without a gate, those tools are left out."""
    native = {item.name for item in toolset.native_tools}
    sources = {item.name: source_of(item, native) for item in tools}
    asking = {name: source for name, source in sources.items() if toolset.approvals.asks(name, source)}
    if gate is None:
        return GuardedTools([item for item in tools if item.name not in asking])
    return GuardedTools(tools, [ApprovalMiddleware(gate, asking)] if asking else [])


def run_gate(database: Database, place: RunStepRef | None, settings: Settings) -> ApprovalGate | None:
    """The gate of a recorded run's step; None outside one, where nobody can be asked."""
    if place is None:
        return None
    return RunApprovalGate(database, place, approval_limits(settings))
