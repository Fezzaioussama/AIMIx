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

The wait counts toward the step's AGENT_TIMEOUT_SECONDS, which is why a
request never waits longer than that. The first request a step's gate records
while nothing else of the run is pending also tells the owner that the run
waits (``GateHooks.on_waiting``, the notifier's email), off the loop. A step's
``ask_user`` question goes through the same gate (``ask_question``): recorded as
a question, answered or skipped from the run report, the answer handed back.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from langchain_core.tools import BaseTool

from api.db import Database
from api.models import (
    TOOL_NAME_MAX_LENGTH,
    TOOL_SOURCE_MAX_LENGTH,
    ApprovalKind,
    ApprovalStatus,
    RunApproval,
)
from api.repositories import approvals as repository
from api.services.agent_types import RunStepRef
from api.services.approvals.decisions import Decision, settle
from api.services.approvals.preview import preview_arguments
from api.services.run_recorder import utcnow
from api.services.tool_catalog import NATIVE_SOURCE, describe
from api.services.toolbox.questions import ASK_USER, Answer, Question, QuestionOutcome
from config.settings import Settings

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]

#: How a question ended, by what its request became (§5 O); an approved one carries
#: the person's answer.
QUESTION_OUTCOMES: dict[ApprovalStatus, QuestionOutcome] = {
    ApprovalStatus.DECLINED: QuestionOutcome.SKIPPED,
    ApprovalStatus.EXPIRED: QuestionOutcome.UNANSWERED,
}


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


#: Tells the run's owner that it waits: the database and the run's id.
WaitingNotice = Callable[[Database, int], object]


@dataclass(frozen=True)
class GateHooks:
    """What a gate calls besides the database: the clock, and who is told that the
    run waits (None tells nobody)."""

    clock: Clock = utcnow
    on_waiting: WaitingNotice | None = None


class RunApprovalGate:
    """The gate of one step of a recorded run, kept in the database (§7 Adapter)."""

    def __init__(
        self,
        database: Database,
        place: RunStepRef,
        limits: ApprovalLimits,
        hooks: GateHooks = GateHooks(),
    ) -> None:
        self._database = database
        self._place = place
        self._limits = limits
        self._clock = hooks.clock
        self._on_waiting = hooks.on_waiting
        #: The owner is told once per step at most: later requests find them told.
        self._told = False

    async def ask(self, request: ToolRequest) -> ApprovalStatus:
        approval = self._record(request)
        if approval is None:
            # The run was stopped while its step was working: nobody is left to ask.
            return ApprovalStatus.EXPIRED
        try:
            await self._tell_owner(approval)
            return await self._answer(approval)
        except asyncio.CancelledError:
            self._expire(approval)
            raise

    async def ask_question(self, question: Question) -> Answer:
        """Ask the run's owner ``question`` and wait for the answer, as ``ask`` waits
        for a tool call's OK: they answer or skip it from the run report."""
        approval = self._save(
            tool_name=ASK_USER,
            tool_source=NATIVE_SOURCE,
            tool_description="",
            arguments={"question": question.text, "options": list(question.options)},
            arguments_truncated=False,
            kind=ApprovalKind.QUESTION,
        )
        if approval is None:
            return Answer(QuestionOutcome.UNANSWERED)
        try:
            await self._tell_owner(approval)
            status = await self._answer(approval)
        except asyncio.CancelledError:
            self._expire(approval)
            raise
        if status != ApprovalStatus.APPROVED:
            return Answer(QUESTION_OUTCOMES[status])
        with self._database.session() as session:
            return Answer(QuestionOutcome.ANSWERED, repository.answer_of(session, approval.id))

    async def _tell_owner(self, approval: RunApproval) -> None:
        """Once per step, when this request is the one that made the run wait."""
        if self._on_waiting is None or self._told:
            return
        self._told = True
        with self._database.session() as session:
            first = repository.pending_count(session, approval.run_id) == 1
        if first:
            await asyncio.to_thread(self._on_waiting, self._database, approval.run_id)

    def _record(self, request: ToolRequest) -> RunApproval | None:
        arguments, truncated = preview_arguments(
            request.arguments, self._limits.arguments_max_chars
        )
        return self._save(
            tool_name=request.tool.name[:TOOL_NAME_MAX_LENGTH],
            tool_source=request.source[:TOOL_SOURCE_MAX_LENGTH],
            tool_description=describe(request.tool, self._limits.description_max_chars),
            arguments=arguments,
            arguments_truncated=truncated,
        )

    def _save(self, **request: Any) -> RunApproval | None:
        """Save one request (a tool call's, a question's) and show the run waiting;
        None when the run is no longer executing."""
        now = self._clock()
        new = repository.NewApproval(
            run_id=self._place.run_id,
            step_order=self._place.step_order,
            created_at=now,
            expires_at=now + timedelta(seconds=self._limits.timeout_seconds),
            **request,
        )
        with self._database.session() as session:
            approval = repository.ask(session, new)
        # Ids and the tool's name only: arguments can hold anything (§6).
        logger.info(
            "approval.requested run_id=%s step=%s tool=%s approval_id=%s",
            new.run_id,
            new.step_order,
            new.tool_name,
            approval.id if approval else None,
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
            return settle(session, approval, Decision(ApprovalStatus.EXPIRED), self._clock())
