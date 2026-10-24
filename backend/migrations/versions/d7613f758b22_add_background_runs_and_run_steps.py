"""Add background pipeline runs and their steps.

Revision ID: d7613f758b22
Revises: b4b5fd007505
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7613f758b22"
down_revision: str | None = "b4b5fd007505"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUN_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled", "interrupted")
STEP_STATUSES = ("pending", "running", "succeeded", "failed", "cancelled")


def _status(name: str, values: tuple[str, ...]) -> sa.Enum:
    # A plain VARCHAR(16): no native enum type and no CHECK constraint.
    return sa.Enum(*values, name=name, native_enum=False, length=16)


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("pipeline_id", sa.Integer(), nullable=True),
        sa.Column("pipeline_name", sa.String(length=255), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("input_values", sa.JSON(), nullable=False),
        sa.Column("status", _status("runstatus", RUN_STATUSES), nullable=False),
        sa.Column("final_output", sa.Text(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["pipeline_id"],
            ["pipelines.id"],
            name=op.f("fk_runs_pipeline_id_pipelines"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_runs_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runs")),
    )
    op.create_index(op.f("ix_runs_pipeline_id"), "runs", ["pipeline_id"], unique=False)
    op.create_index(op.f("ix_runs_user_id"), "runs", ["user_id"], unique=False)

    op.create_table(
        "run_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("status", _status("stepstatus", STEP_STATUSES), nullable=False),
        sa.Column("is_output", sa.Boolean(), nullable=False),
        sa.Column("input_used", sa.Text(), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        sa.Column("tool_calls", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name=op.f("fk_run_steps_run_id_runs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_run_steps")),
        sa.UniqueConstraint("run_id", "step_order", name="uq_run_step_order"),
    )


def downgrade() -> None:
    op.drop_table("run_steps")
    op.drop_index(op.f("ix_runs_user_id"), table_name="runs")
    op.drop_index(op.f("ix_runs_pipeline_id"), table_name="runs")
    op.drop_table("runs")
