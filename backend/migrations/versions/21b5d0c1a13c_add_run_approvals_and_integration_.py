"""Add approval gates: run approvals, and each integration's "ask me first".

Runs gain the status ``waiting``; ``runs.status`` is a plain VARCHAR(16)
without a CHECK constraint, so the new value needs no schema change.

Revision ID: 21b5d0c1a13c
Revises: d7613f758b22
Create Date: 2026-10-24 23:36:47.366028
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "21b5d0c1a13c"
down_revision: str | None = "d7613f758b22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPROVAL_STATUSES = ("pending", "approved", "declined", "expired")


def upgrade() -> None:
    op.create_table(
        "run_approvals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("tool_source", sa.String(length=64), nullable=False),
        sa.Column("tool_description", sa.Text(), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("arguments_truncated", sa.Boolean(), nullable=False),
        # A plain VARCHAR(16): no native enum type and no CHECK constraint.
        sa.Column(
            "status",
            sa.Enum(*APPROVAL_STATUSES, name="approvalstatus", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            name=op.f("fk_run_approvals_run_id_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_run_approvals")),
    )
    with op.batch_alter_table("run_approvals", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_run_approvals_run_id"), ["run_id"], unique=False)

    # Existing integrations ask first too: the safe default. A plain string
    # default, never an expression, so SQLite adds the column in place.
    with op.batch_alter_table("integrations", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("require_approval", sa.Boolean(), server_default="1", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("integrations", schema=None) as batch_op:
        batch_op.drop_column("require_approval")

    with op.batch_alter_table("run_approvals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_run_approvals_run_id"))

    op.drop_table("run_approvals")
