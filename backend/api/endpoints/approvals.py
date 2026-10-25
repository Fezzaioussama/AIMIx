"""Answer a run's tool call that waits for approval: approve lets the tool
act, decline makes it report a refusal to its agent. Each endpoint validates,
calls the run service and shapes the result (AGENTS.md §2)."""

from __future__ import annotations

from fastapi import APIRouter

from api.deps import CurrentUser, Runs
from api.models import ApprovalStatus
from api.schemas.runs import RunOut
from api.services.approvals.decisions import ApprovalAnswer

router = APIRouter(tags=["approvals"])


@router.post("/runs/{run_id}/approvals/{approval_id}/approve")
def approve_tool_call(run_id: int, approval_id: int, user: CurrentUser, runs: Runs) -> RunOut:
    """Let the waiting tool call act. Approving it again changes nothing."""
    given = ApprovalAnswer(run_id, approval_id, ApprovalStatus.APPROVED)
    return RunOut.model_validate(runs.answer_approval(user, given))


@router.post("/runs/{run_id}/approvals/{approval_id}/decline")
def decline_tool_call(run_id: int, approval_id: int, user: CurrentUser, runs: Runs) -> RunOut:
    """Refuse the waiting tool call; its agent is told. Declining it again changes nothing."""
    given = ApprovalAnswer(run_id, approval_id, ApprovalStatus.DECLINED)
    return RunOut.model_validate(runs.answer_approval(user, given))
