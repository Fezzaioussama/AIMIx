"""Decorator over tool calls (AGENTS.md §7): a tool that must ask first waits at
the run's approval gate and acts only once approved.

It hooks into LangChain's agent loop (``awrap_tool_call``), so the wrapped tool
keeps its own argument checks, result format and error handling. A declined or
expired request reaches the agent as an error result it can react to; the run
goes on, and the step's trace shows the call as ``error``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from api.models import ApprovalStatus
from api.services.approvals.gate import ApprovalGate, ToolRequest

ToolCallResult = ToolMessage | Command[Any]

#: What the agent is told when the tool did not act, by outcome (§5 O).
NOT_ACTED: dict[ApprovalStatus, str] = {
    ApprovalStatus.DECLINED: "The user declined this action, so it was not carried out.",
    ApprovalStatus.EXPIRED: "The user did not answer in time, so this action was not carried out.",
}


class ApprovalMiddleware(AgentMiddleware):
    """Holds each call of the gated tools until the run's owner answers."""

    def __init__(self, gate: ApprovalGate, sources: Mapping[str, str]) -> None:
        """``sources`` maps each tool that asks first to where it comes from."""
        super().__init__()
        self._gate = gate
        self._sources = dict(sources)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolCallResult]],
    ) -> ToolCallResult:
        call = request.tool_call
        source = self._sources.get(call["name"])
        if source is None or request.tool is None:
            return await handler(request)
        asked = ToolRequest(request.tool, source, call.get("args") or {})
        status = await self._gate.ask(asked)
        if status == ApprovalStatus.APPROVED:
            return await handler(request)
        return ToolMessage(
            content=NOT_ACTED[status],
            tool_call_id=call.get("id") or "",
            name=call["name"],
            status="error",
        )
