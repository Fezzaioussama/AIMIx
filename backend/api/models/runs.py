"""A run of a pipeline, its steps and the tool calls that wait for its owner's OK, with
the statuses each of them goes through."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint, and_
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import (
    ERROR_CODE_MAX_LENGTH,
    MODEL_ID_MAX_LENGTH,
    PIPELINE_NAME_MAX_LENGTH,
    STATUS_MAX_LENGTH,
    STEP_TITLE_MAX_LENGTH,
    TOOL_NAME_MAX_LENGTH,
    TOOL_SOURCE_MAX_LENGTH,
    Base,
    _status_type,
    _utcnow,
)


class RunStatus(str, Enum):
    """Where a run is. ``queued``, ``running`` and ``waiting`` are active; the
    rest are final."""

    QUEUED = "queued"
    RUNNING = "running"
    #: Running, with a tool call waiting for the owner's approval.
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    #: The server stopped (a restart or redeploy) while the run was active.
    INTERRUPTED = "interrupted"


#: A run in one of these has work left to do: it cannot be deleted or resumed.
ACTIVE_RUN_STATUSES = frozenset({RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.WAITING})
#: A run that stopped before the end can continue from the first unfinished stage.
RESUMABLE_RUN_STATUSES = frozenset({RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.INTERRUPTED})


class StepStatus(str, Enum):
    """Where one step of a run is."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    #: Its condition did not hold, so it did not run. Final, like ``succeeded``:
    #: a resumed run keeps it.
    SKIPPED = "skipped"


#: The steps a resumed run keeps as they are, whose agents it does not run again.
COMPLETED_STEP_STATUSES = frozenset({StepStatus.SUCCEEDED, StepStatus.SKIPPED})


class ApprovalStatus(str, Enum):
    """Where a tool call that must ask the run's owner first is. Only ``pending`` changes."""

    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"
    #: Nobody decided in time, or the run stopped first: the tool did not act.
    EXPIRED = "expired"


class ApprovalKind(str, Enum):
    """What a request at the gate asks: the OK for a tool call, or (``ask_user``)
    an answer to a question."""

    APPROVAL = "approval"
    QUESTION = "question"


class RunTrigger(str, Enum):
    """What started a run: its owner (the builder, the Runs screen or the API),
    one of their schedules, the chat agent's run_pipeline tool, or another app
    calling the pipeline's webhook."""

    MANUAL = "manual"
    SCHEDULE = "schedule"
    CHAT = "chat"
    WEBHOOK = "webhook"


#: Runs someone watches: started by hand or from the chat. A schedule's or a webhook's
#: run has nobody to ask a question (``toolbox/questions``).
ATTENDED_TRIGGERS = frozenset({RunTrigger.MANUAL, RunTrigger.CHAT})


class Run(Base):
    """One execution of a pipeline: history, live progress and resumable state.

    ``definition`` is the pipeline as it was when the run was started (the JSON
    form of ``services/multiagent/contracts.PipelineSpec``), so editing the
    pipeline later never changes a run, and deleting it only clears
    ``pipeline_id``. ``input_text`` / ``input_values`` are what the run was
    started with. Empty error fields mean there was no error.
    """

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    pipeline_id: Mapped[int | None] = mapped_column(
        ForeignKey("pipelines.id", ondelete="SET NULL"), index=True
    )
    pipeline_name: Mapped[str] = mapped_column(String(PIPELINE_NAME_MAX_LENGTH))
    definition: Mapped[dict[str, Any]] = mapped_column(JSON)
    input_text: Mapped[str] = mapped_column(Text, default="")
    input_values: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    #: ``schedule_id`` is the schedule that started it, until that is deleted.
    trigger: Mapped[RunTrigger] = mapped_column(_status_type(RunTrigger), default=RunTrigger.MANUAL)
    schedule_id: Mapped[int | None] = mapped_column(
        ForeignKey("schedules.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[RunStatus] = mapped_column(_status_type(RunStatus), default=RunStatus.QUEUED)
    final_output: Mapped[str] = mapped_column(Text, default="")
    error_code: Mapped[str] = mapped_column(String(ERROR_CODE_MAX_LENGTH), default="")
    error_detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    #: The run's spending limits, set when it starts and raised when it resumes;
    #: None is no limit. What it spent is the sum of its steps' usage.
    max_cost_usd: Mapped[float | None]
    max_tokens: Mapped[int | None]

    steps: Mapped[list[RunStep]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="(RunStep.stage, RunStep.step_order)",
    )
    #: Tool calls waiting for the owner's decision, oldest first. Read-only:
    #: approvals are written by ``repositories/approvals`` and deleted with the run.
    pending_approvals: Mapped[list[RunApproval]] = relationship(
        primaryjoin=lambda: and_(
            Run.id == RunApproval.run_id, RunApproval.status == ApprovalStatus.PENDING
        ),
        order_by=lambda: RunApproval.id,
        viewonly=True,
    )


class RunStep(Base):
    """One step of a run: the input it used, what it produced and how it went.

    ``tool_calls`` lists ``{"name", "status"}`` per tool call — never the
    arguments or results. The token and cost columns grow with each model call
    the step's agent makes, over every attempt: resuming a run never resets them.

    A step inside a review loop that runs again updates this same row (its
    output is replaced, its usage keeps adding up): ``rounds`` is the round the
    row is in, 1 for every other step. ``verdict`` is what a reviewer's last
    answer said (``pass`` or ``revise``), None for any other step or when it
    gave none; it is what lets a resumed run pick a loop up where it was.
    """

    __tablename__ = "run_steps"
    __table_args__ = (UniqueConstraint("run_id", "step_order", name="uq_run_step_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    step_order: Mapped[int]
    stage: Mapped[int]
    title: Mapped[str] = mapped_column(String(STEP_TITLE_MAX_LENGTH), default="")
    model: Mapped[str] = mapped_column(String(MODEL_ID_MAX_LENGTH))
    status: Mapped[StepStatus] = mapped_column(_status_type(StepStatus), default=StepStatus.PENDING)
    is_output: Mapped[bool] = mapped_column(default=False)
    input_used: Mapped[str] = mapped_column(Text, default="")
    output: Mapped[str] = mapped_column(Text, default="")
    tool_calls: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    error_code: Mapped[str] = mapped_column(String(ERROR_CODE_MAX_LENGTH), default="")
    error_detail: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    #: USD, the calls whose cost is known added up; None when none is.
    cost_usd: Mapped[float | None]
    rounds: Mapped[int] = mapped_column(default=1)
    verdict: Mapped[str | None] = mapped_column(String(STATUS_MAX_LENGTH))

    run: Mapped[Run] = relationship(back_populates="steps")


class RunApproval(Base):
    """A step's tool call that waits for the run owner's OK before it acts.

    ``arguments`` holds the call's arguments as a JSON object, for the owner to
    read, shortened to fit APPROVAL_ARGUMENTS_MAX_CHARS (``arguments_truncated``);
    they are never logged. ``tool_source`` is where the tool comes from (an
    integration's name, ``MCP`` or ``AIMIx``). ``expires_at`` is when an
    unanswered request counts as declined. ``kind`` says whether the request is
    the OK for a tool call or (``ask_user``) a question, whose answer ``answer``
    holds.
    """

    __tablename__ = "run_approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    step_order: Mapped[int]
    tool_name: Mapped[str] = mapped_column(String(TOOL_NAME_MAX_LENGTH))
    tool_source: Mapped[str] = mapped_column(String(TOOL_SOURCE_MAX_LENGTH), default="")
    tool_description: Mapped[str] = mapped_column(Text, default="")
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    arguments_truncated: Mapped[bool] = mapped_column(default=False)
    #: The OK for a tool call, or (ask_user) an answer to a question.
    kind: Mapped[ApprovalKind] = mapped_column(
        _status_type(ApprovalKind), default=ApprovalKind.APPROVAL
    )
    #: What the person answered a question; "" otherwise.
    answer: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[ApprovalStatus] = mapped_column(
        _status_type(ApprovalStatus), default=ApprovalStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    expires_at: Mapped[datetime]
    decided_at: Mapped[datetime | None]

    def has_expired(self, now: datetime) -> bool:
        """Whether the time to decide is over. SQLite reads timestamps back
        without their UTC offset; every one is stored in UTC."""
        deadline = self.expires_at
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return now >= deadline
