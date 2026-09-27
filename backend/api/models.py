"""Persistence and the invariants that belong to each entity (AGENTS.md §2)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import ForeignKey, MetaData, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

STEP_TITLE_MAX_LENGTH = 100
USERNAME_MAX_LENGTH = 150
PIPELINE_NAME_MAX_LENGTH = 255
MODEL_ID_MAX_LENGTH = 200


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
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    pipelines: Mapped[list[Pipeline]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Pipeline(Base):
    """A named set of LLM steps owned by one user."""

    __tablename__ = "pipelines"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(PIPELINE_NAME_MAX_LENGTH))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    user: Mapped[User] = relationship(back_populates="pipelines")
    steps: Mapped[list[PipelineStep]] = relationship(
        back_populates="pipeline",
        cascade="all, delete-orphan",
        order_by="(PipelineStep.stage, PipelineStep.order)",
    )


class PipelineStep(Base):
    """One step of a pipeline. ``prompt`` may contain the {input} placeholder,
    which the runner substitutes with the previous stage's output.

    Steps sharing a ``stage`` run in parallel on the same input; stages run in
    ascending order, so ``stage == order`` for every step is a plain chain.

    ``is_output`` marks a step whose result is a deliverable of the pipeline
    rather than intermediate work. When no step is marked, the last stage's
    steps are the outputs. Output steps still feed any later stage.
    """

    __tablename__ = "pipeline_steps"
    __table_args__ = (UniqueConstraint("pipeline_id", "order", name="uq_step_order_per_pipeline"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_id: Mapped[int] = mapped_column(ForeignKey("pipelines.id", ondelete="CASCADE"))
    order: Mapped[int]
    stage: Mapped[int]
    title: Mapped[str] = mapped_column(String(STEP_TITLE_MAX_LENGTH), default="")
    is_output: Mapped[bool] = mapped_column(default=False)
    prompt: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(MODEL_ID_MAX_LENGTH))

    pipeline: Mapped[Pipeline] = relationship(back_populates="steps")
