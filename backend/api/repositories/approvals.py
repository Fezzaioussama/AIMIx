"""Data access for approval gates (AGENTS.md §7 Repository).

A run's tool call that must ask the run's owner first is a ``RunApproval``.
The run shows ``waiting`` while any of its approvals is pending: recording a
request moves it there, and settling the last pending one moves it back to
``running``, each in the same transaction as the approval's own change. Every
change to an approval is a compare-and-set from ``pending``, so the owner's
answer, the gate's timeout and a stopped run never overwrite one another.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy import Select, exists, select, update
from sqlalchemy.orm import Session

from api.exceptions import NotFound
from api.models import ApprovalStatus, Run, RunApproval, RunStatus
from api.repositories.bulk import changed

_PENDING = ApprovalStatus.PENDING


@dataclass(frozen=True)
class NewApproval:
    """A tool call to hold for the owner: what it is and until when it waits."""

    run_id: int
    step_order: int
    tool_name: str
    tool_source: str
    tool_description: str
    arguments: str
    arguments_truncated: bool
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class Settlement:
    """How one pending approval ends: approved, declined or expired."""

    run_id: int
    approval_id: int
    status: ApprovalStatus
    decided_at: datetime


def ask(session: Session, new: NewApproval) -> RunApproval:
    """Save a pending approval and show its run as waiting, in one transaction."""
    approval = RunApproval(**asdict(new), status=_PENDING)
    session.add(approval)
    changed(
        session,
        update(Run)
        .where(Run.id == new.run_id, Run.status == RunStatus.RUNNING)
        .values(status=RunStatus.WAITING),
    )
    session.commit()
    return approval


def get_in_run(session: Session, run_id: int, approval_id: int) -> RunApproval:
    """One approval of a run the caller already owns, or NotFound."""
    approval = session.scalar(
        select(RunApproval).where(RunApproval.id == approval_id, RunApproval.run_id == run_id)
    )
    if approval is None:
        raise NotFound(f"Approval {approval_id} was not found.")
    return approval


def status_of(session: Session, approval_id: int) -> ApprovalStatus | None:
    """Where an approval is now; None once it was deleted with its run."""
    return session.scalar(select(RunApproval.status).where(RunApproval.id == approval_id))


def settle(session: Session, settlement: Settlement) -> bool:
    """End a pending approval (compare-and-set); the run is running again once
    nothing else of it is pending. False when it was no longer pending."""
    settled = changed(
        session,
        update(RunApproval)
        .where(
            RunApproval.id == settlement.approval_id,
            RunApproval.run_id == settlement.run_id,
            RunApproval.status == _PENDING,
        )
        .values(status=settlement.status, decided_at=settlement.decided_at),
    )
    if settled:
        _resume_if_answered(session, settlement.run_id)
    session.commit()
    return settled == 1


def _resume_if_answered(session: Session, run_id: int) -> None:
    pending = exists().where(RunApproval.run_id == run_id, RunApproval.status == _PENDING)
    changed(
        session,
        update(Run)
        .where(Run.id == run_id, Run.status == RunStatus.WAITING, ~pending)
        .values(status=RunStatus.RUNNING),
    )


def expire_pending(
    session: Session, run_ids: Collection[int] | Select[tuple[int]], now: datetime
) -> int:
    """Expire what the given runs (ids, or a SELECT of ids) still have pending,
    as their runs end. Part of the caller's transaction: it does not commit."""
    return changed(
        session,
        update(RunApproval)
        .where(RunApproval.run_id.in_(run_ids), RunApproval.status == _PENDING)
        .values(status=ApprovalStatus.EXPIRED, decided_at=now),
    )
