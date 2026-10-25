"""Contracts for approval gates: a run's tool call that waits for its owner."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from api.models import ApprovalStatus
from api.schemas.common import UtcDateTime


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
    #: The call's arguments as JSON text, cut at APPROVAL_ARGUMENTS_MAX_CHARS.
    arguments: str
    arguments_truncated: bool
    status: ApprovalStatus
    created_at: UtcDateTime
    #: Unanswered by then, the request expires and the tool does not act.
    expires_at: UtcDateTime
