"""Answer a run's request: approve lets a waiting tool call act, decline makes it
report a refusal to its agent (or skips a question), answer replies to a question
the agent asked (``ask_user``). Each endpoint validates,
calls the run service and shapes the result (AGENTS.md §2)."""

from __future__ import annotations

from fastapi import APIRouter

from api.deps import CurrentUser, RunAnswers, Runs
from api.models import ApprovalStatus
from api.schemas.approvals import QuestionAnswerIn
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


@router.post("/runs/{run_id}/approvals/{approval_id}/answer")
def answer_question(
    run_id: int, approval_id: int, body: QuestionAnswerIn, answering: RunAnswers
) -> RunOut:
    """Answer a question the run's agent asked (``ask_user``); the agent reads it.
    Skipping it is ``/decline``."""
    given = ApprovalAnswer(run_id, approval_id, ApprovalStatus.APPROVED, body.answer)
    return RunOut.model_validate(answering.runs.answer_approval(answering.user, given))
