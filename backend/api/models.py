"""Persistence and the invariants that belong to each entity (AGENTS.md §2)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import JSON, ForeignKey, MetaData, String, Text, UniqueConstraint, and_
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

STEP_TITLE_MAX_LENGTH = 100
STEP_ROLE_MAX_LENGTH = 100
STEP_EXPECTED_OUTPUT_MAX_LENGTH = 500
USERNAME_MAX_LENGTH = 150
PIPELINE_NAME_MAX_LENGTH = 255
#: A named run input is referenced as ``{name}`` in step prompts. ``input`` is
#: reserved because ``{input}`` already means a stage's input.
PIPELINE_INPUT_NAME_PATTERN = r"[a-z][a-z0-9_]*"
PIPELINE_INPUT_NAME_MAX_LENGTH = 40
PIPELINE_INPUT_LABEL_MAX_LENGTH = 100
PIPELINE_INPUT_DESCRIPTION_MAX_LENGTH = 300
PIPELINE_MAX_INPUTS = 20
RESERVED_INPUT_NAME = "input"
MODEL_ID_MAX_LENGTH = 200
PROVIDER_NAME_MAX_LENGTH = 50
API_KEY_HINT_LENGTH = 4
#: An integration's name prefixes its tools' names (``<name>_<tool>``).
INTEGRATION_NAME_PATTERN = r"[a-z][a-z0-9_]{1,30}"
INTEGRATION_NAME_MAX_LENGTH = 31
INTEGRATION_URL_MAX_LENGTH = 2048
STATUS_MAX_LENGTH = 16
ERROR_CODE_MAX_LENGTH = 64
#: Model APIs accept tool names up to 64 characters; longer ones are cut when stored.
TOOL_NAME_MAX_LENGTH = 64
#: Where a tool comes from: an integration's name, or a fixed label.
TOOL_SOURCE_MAX_LENGTH = 64


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


#: Deterministic constraint names, so Alembic migrations can refer to them.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(USERNAME_MAX_LENGTH), unique=True)
    #: ``pbkdf2_sha256$<iterations>$<salt>$<hash>`` — the format Django used, so
    #: accounts imported from the previous backend keep their passwords.
    password_hash: Mapped[str] = mapped_column(String(256))
    #: SHA-256 of the one currently valid refresh token. Keeping only a hash
    #: makes refresh rotation and logout possible without storing bearer secrets.
    refresh_token_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    #: The LLM provider this user's requests go to; None means LLM_PROVIDER.
    llm_provider: Mapped[str | None] = mapped_column(String(PROVIDER_NAME_MAX_LENGTH))

    pipelines: Mapped[list[Pipeline]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    provider_settings: Mapped[list[ProviderSetting]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RateLimitBucket(Base):
    """A cross-process fixed-window counter containing no raw client address."""

    __tablename__ = "rate_limit_buckets"
    __table_args__ = (UniqueConstraint("identity_hash", "action", name="uq_rate_limit_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    identity_hash: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    window_started_at: Mapped[datetime] = mapped_column(default=_utcnow)
    hits: Mapped[int] = mapped_column(default=0)


class ProviderSetting(Base):
    """One user's API key and default model for one LLM provider.

    The key is stored encrypted (``api.security.SecretBox``) and never leaves the
    server; ``api_key_hint`` keeps its last characters so the UI can tell keys
    apart. Empty strings mean "not saved": the environment's value applies.
    """

    __tablename__ = "provider_settings"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_provider_setting_per_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(PROVIDER_NAME_MAX_LENGTH))
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    api_key_hint: Mapped[str] = mapped_column(String(API_KEY_HINT_LENGTH), default="")
    default_model: Mapped[str] = mapped_column(String(MODEL_ID_MAX_LENGTH), default="")

    user: Mapped[User] = relationship(back_populates="provider_settings")


class Pipeline(Base):
    """A named set of LLM steps owned by one user.

    ``inputs`` declares the named values every run is given, in display order,
    as ``{"name", "label", "description"}`` objects. Empty means the pipeline
    runs on one free-text input.
    """

    __tablename__ = "pipelines"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(PIPELINE_NAME_MAX_LENGTH))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    inputs: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)

    user: Mapped[User] = relationship(back_populates="pipelines")
    steps: Mapped[list[PipelineStep]] = relationship(
        back_populates="pipeline",
        cascade="all, delete-orphan",
        order_by="(PipelineStep.stage, PipelineStep.order)",
    )


class PipelineStep(Base):
    """One step of a pipeline. ``prompt`` may contain the {input} placeholder,
    which the runner substitutes with the previous stage's output, and
    ``{name}`` for any of the pipeline's named inputs.

    Steps sharing a ``stage`` run in parallel on the same input; stages run in
    ascending order, so ``stage == order`` for every step is a plain chain.

    ``is_output`` marks a step whose result is a deliverable of the pipeline
    rather than intermediate work. When no step is marked, the last stage's
    steps are the outputs. Output steps still feed any later stage.
    ``expected_output`` tells the step's agent what to deliver; empty leaves
    that to the prompt.
    """

    __tablename__ = "pipeline_steps"
    __table_args__ = (UniqueConstraint("pipeline_id", "order", name="uq_step_order_per_pipeline"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_id: Mapped[int] = mapped_column(ForeignKey("pipelines.id", ondelete="CASCADE"))
    order: Mapped[int]
    stage: Mapped[int]
    title: Mapped[str] = mapped_column(String(STEP_TITLE_MAX_LENGTH), default="")
    role: Mapped[str] = mapped_column(String(STEP_ROLE_MAX_LENGTH), default="")
    allowed_tools: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    is_output: Mapped[bool] = mapped_column(default=False)
    expected_output: Mapped[str] = mapped_column(
        String(STEP_EXPECTED_OUTPUT_MAX_LENGTH), default=""
    )
    prompt: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(MODEL_ID_MAX_LENGTH))

    pipeline: Mapped[Pipeline] = relationship(back_populates="steps")


class Integration(Base):
    """One of a user's own MCP servers, reached over streamable HTTP only.

    Header values are stored encrypted as one JSON object
    (``api.security.SecretBox``) and never leave the server; ``header_hints``
    keeps each header's name and a short hint of its value, as
    ``{"name", "hint"}`` objects, so the UI can tell them apart.
    """

    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_integration_name_per_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(INTEGRATION_NAME_MAX_LENGTH))
    url: Mapped[str] = mapped_column(String(INTEGRATION_URL_MAX_LENGTH))
    headers_encrypted: Mapped[str] = mapped_column(Text, default="")
    header_hints: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(default=True)
    #: Its tools wait for the run owner's OK before they act (approval gates).
    require_approval: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


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


class ApprovalStatus(str, Enum):
    """Where a tool call that must ask the run's owner first is. Only ``pending`` changes."""

    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"
    #: Nobody decided in time, or the run stopped first: the tool did not act.
    EXPIRED = "expired"


def _status_type(statuses: type[Enum]) -> SQLEnum:
    """Stored as the lowercase value in a plain string column, read back as the enum."""
    return SQLEnum(
        statuses,
        native_enum=False,
        length=STATUS_MAX_LENGTH,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


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

    run: Mapped[Run] = relationship(back_populates="steps")


class RunApproval(Base):
    """A step's tool call that waits for the run owner's OK before it acts.

    ``arguments`` holds the call's arguments as a JSON object, for the owner to
    read, shortened to fit APPROVAL_ARGUMENTS_MAX_CHARS (``arguments_truncated``);
    they are never logged. ``tool_source`` is where the tool comes from (an
    integration's name, ``MCP`` or ``AIMIx``). ``expires_at`` is when an
    unanswered request counts as declined.
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
