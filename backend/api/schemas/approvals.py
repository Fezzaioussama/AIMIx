"""Contracts for approval gates: a run's tool call that waits for its owner."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.models import ApprovalKind, ApprovalStatus
from api.schemas.common import NonBlank, UtcDateTime

#: The most a person may write in answer to an agent's question.
ANSWER_MAX_LENGTH = 4_000


class RunApprovalOut(BaseModel):
    """A tool call held until the run's owner approves or declines it."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    #: The run step whose agent wants to use the tool.
    step_order: int
    tool_name: str
    #: Where the tool comes from: an integration's name, ``MCP`` or ``AIMIx``.
    tool_source: str
    tool_description: str
    #: The call's arguments, long text values shortened to fit
    #: APPROVAL_ARGUMENTS_MAX_CHARS (``arguments_truncated`` says whether any was).
    arguments: dict[str, Any]
    arguments_truncated: bool
    #: The OK for a tool call, or (ask_user) an answer to a question.
    kind: ApprovalKind
    #: What the person answered a question; "" otherwise.
    answer: str
    status: ApprovalStatus
    created_at: UtcDateTime
    #: Unanswered by then, the request expires and the tool does not act.
    expires_at: UtcDateTime


class QuestionAnswerIn(BaseModel):
    """The person's answer to a question an agent asked (ask_user)."""

    answer: NonBlank = Field(max_length=ANSWER_MAX_LENGTH)
