"""The approval gate: a tool call that must ask first waits here for the run
owner's answer.

``RunApprovalGate`` records the request as a ``RunApproval`` (the run shows
``waiting``) and then reads it back every APPROVAL_POLL_SECONDS between
``asyncio.sleep`` calls: the run's event loop keeps serving other runs, and an
answer given by any request thread, or any process sharing the database,
reaches it. A request not answered by its ``expires_at`` expires and counts
as declined; so does one whose wait is cancelled (the run was stopped, a
parallel step failed, the step ran out of time, the server shut down). Each
write is a short transaction on the run's loop, as in ``run_recorder``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from langchain_core.tools import BaseTool

from api.db import Database
from api.models import TOOL_NAME_MAX_LENGTH, TOOL_SOURCE_MAX_LENGTH, ApprovalStatus, RunApproval
from api.repositories import approvals as repository
from api.services.agent_types import RunStepRef
from api.services.approvals.decisions import settle
from api.services.run_recorder import utcnow
from api.services.tool_catalog import describe
from config.settings import Settings

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]


@dataclass(frozen=True)
class ToolRequest:
    """One tool call that waits for the run's owner (§7 Value Object)."""

    tool: BaseTool
    #: Where the tool comes from, as ``tool_catalog.source_of`` names it.
    source: str
    arguments: Mapping[str, Any]


class ApprovalGate(Protocol):
    """Port: ask the run's owner about one tool call and wait for the answer,
    APPROVED, DECLINED or EXPIRED."""

    async def ask(self, request: ToolRequest) -> ApprovalStatus: ...


@dataclass(frozen=True)
class ApprovalLimits:
    timeout_seconds: float
    poll_seconds: float
    arguments_max_chars: int
    description_max_chars: int


def approval_limits(settings: Settings) -> ApprovalLimits:
    """From settings. A request never waits longer than a step may last
    (AGENT_TIMEOUT_SECONDS), so its deadline is one the owner can meet."""
    return ApprovalLimits(
        timeout_seconds=min(settings.approval_timeout_seconds, settings.agent_timeout_seconds),
        poll_seconds=settings.approval_poll_seconds,
        arguments_max_chars=settings.approval_arguments_max_chars,
        description_max_chars=settings.agent_tool_description_max_chars,
    )


def preview(arguments: Mapping[str, Any], max_chars: int) -> tuple[str, bool]:
    """The arguments as JSON text for the owner to read, and whether it was cut."""
    text = json.dumps(arguments, ensure_ascii=False, default=str)
    return (text, False) if len(text) <= max_chars else (text[:max_chars], True)


class RunApprovalGate:
    """The gate of one step of a recorded run, kept in the database (§7 Adapter)."""

    def __init__(
        self, database: Database, place: RunStepRef, limits: ApprovalLimits, clock: Clock = utcnow
    ) -> None:
        self._database = database
        self._place = place
        self._limits = limits
        self._clock = clock

    async def ask(self, request: ToolRequest) -> ApprovalStatus:
        approval = self._record(request)
        try:
            return await self._answer(approval)
        except asyncio.CancelledError:
            self._expire(approval)
            raise

    def _record(self, request: ToolRequest) -> RunApproval:
        now = self._clock()
        arguments, truncated = preview(request.arguments, self._limits.arguments_max_chars)
        new = repository.NewApproval(
            run_id=self._place.run_id,
            step_order=self._place.step_order,
            tool_name=request.tool.name[:TOOL_NAME_MAX_LENGTH],
            tool_source=request.source[:TOOL_SOURCE_MAX_LENGTH],
            tool_description=describe(request.tool, self._limits.description_max_chars),
            arguments=arguments,
            arguments_truncated=truncated,
            created_at=now,
            expires_at=now + timedelta(seconds=self._limits.timeout_seconds),
        )
        with self._database.session() as session:
            approval = repository.ask(session, new)
        # Ids and the tool's name only: arguments can hold anything (§6).
        logger.info(
            "approval.requested run_id=%s approval_id=%s step=%s tool=%s",
            approval.run_id,
            approval.id,
            approval.step_order,
            approval.tool_name,
        )
        return approval

    async def _answer(self, approval: RunApproval) -> ApprovalStatus:
        while (status := self._status(approval)) == ApprovalStatus.PENDING:
            if approval.has_expired(self._clock()):
                return self._expire(approval)
            await asyncio.sleep(self._limits.poll_seconds)
        return status

    def _status(self, approval: RunApproval) -> ApprovalStatus:
        with self._database.session() as session:
            return repository.status_of(session, approval.id) or ApprovalStatus.EXPIRED

    def _expire(self, approval: RunApproval) -> ApprovalStatus:
        with self._database.session() as session:
            return settle(session, approval, ApprovalStatus.EXPIRED, self._clock())
