"""Persistence and the invariants that belong to each entity (AGENTS.md §2)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, ForeignKey, MetaData, String, Text, UniqueConstraint
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
