"""A pipeline (a mission once it is open in Missions) and its steps."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import (
    MODEL_ID_MAX_LENGTH,
    PIPELINE_NAME_MAX_LENGTH,
    STEP_EXPECTED_OUTPUT_MAX_LENGTH,
    STEP_ROLE_MAX_LENGTH,
    STEP_TITLE_MAX_LENGTH,
    Base,
    _utcnow,
)

if TYPE_CHECKING:
    from api.models.users import User


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

    ``condition`` makes the step conditional: ``{"source", "operator", "value"}``,
    or None to always run it (``services/multiagent/conditions``). ``review``
    makes it a reviewer that can send the work back:
    ``{"send_back_to_stage", "max_rounds"}``, or None (``multiagent/reviews``).
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
    condition: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    review: Mapped[dict[str, int] | None] = mapped_column(JSON, nullable=True)

    pipeline: Mapped[Pipeline] = relationship(back_populates="steps")
