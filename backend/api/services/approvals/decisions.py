"""How a request at an approval gate ends: the run owner's answer, or expiry.

Answering is idempotent: the same answer twice changes nothing. A request that
already got the other answer, or expired (it was not answered in time, or the
run stopped), cannot change any more, which is a ``Conflict``. An answer that
comes after the request's time is over expires it instead. A question
(``ask_user``) approved is one answered: it needs the text, else it is refused;
declining it skips it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from api.exceptions import Conflict, ValidationFailed
from api.models import ApprovalKind, ApprovalStatus, RunApproval, User
from api.repositories import approvals as repository
from api.repositories import runs as run_repository
from api.services.run_recorder import utcnow

logger = logging.getLogger(__name__)

#: Why an answer is refused, by what the request already is (§5 O).
REFUSALS: dict[ApprovalStatus, str] = {
    ApprovalStatus.APPROVED: "This action was already approved.",
    ApprovalStatus.DECLINED: "This action was already declined.",
    ApprovalStatus.EXPIRED: (
        "This request has expired: it was not answered in time, or the run stopped."
    ),
}


@dataclass(frozen=True)
class Decision:
    """How a request ends: approved (with the answer, for a question), declined
    or expired."""

    status: ApprovalStatus
    answer: str = ""


@dataclass(frozen=True)
class ApprovalAnswer:
    """The owner's answer to one request of one of their runs."""

    run_id: int
    approval_id: int
    #: APPROVED or DECLINED.
    status: ApprovalStatus
    #: The answer to a question (``ask_user``); a tool call's OK needs none.
    text: str = ""


def answer(session: Session, user: User, given: ApprovalAnswer) -> None:
    """Record the answer to a request of one of ``user``'s runs (else NotFound)."""
    run = run_repository.get_owned(session, user, given.run_id)
    approval = repository.get_in_run(session, run.id, given.approval_id)
    status = approval.status
    if status == ApprovalStatus.PENDING:
        _ensure_answered(approval, given)
        now = utcnow()
        decision = (
            Decision(ApprovalStatus.EXPIRED)
            if approval.has_expired(now)
            else Decision(given.status, given.text.strip())
        )
        status = settle(session, approval, decision, now)
    if status != given.status:
        raise Conflict(REFUSALS[status])


def _ensure_answered(approval: RunApproval, given: ApprovalAnswer) -> None:
    """A question approved is a question answered: it needs the text."""
    if (
        approval.kind == ApprovalKind.QUESTION
        and given.status == ApprovalStatus.APPROVED
        and not given.text.strip()
    ):
        raise ValidationFailed("answer: This question needs an answer, or skip it.")


def settle(
    session: Session, approval: RunApproval, decision: Decision, now: datetime
) -> ApprovalStatus:
    """End a pending request as ``decision`` says unless it ended meanwhile (the
    other side of the gate got there first); what it is afterwards."""
    ending = repository.Settlement(
        approval.run_id, approval.id, decision.status, now, decision.answer
    )
    if repository.settle(session, ending):
        log_decided(approval, decision.status)
        return decision.status
    return repository.status_of(session, approval.id) or ApprovalStatus.EXPIRED


def log_decided(approval: RunApproval, outcome: ApprovalStatus) -> None:
    """``approval.decided`` with ids, step, tool and outcome; the arguments are
    never logged (AGENTS.md §6)."""
    logger.info(
        "approval.decided run_id=%s approval_id=%s step=%s tool=%s outcome=%s",
        approval.run_id,
        approval.id,
        approval.step_order,
        approval.tool_name,
        outcome.value,
    )
