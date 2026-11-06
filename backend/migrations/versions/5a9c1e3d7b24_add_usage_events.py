"""Add usage events: what an account's chat and planner calls used, so its spending
of the server's key adds up by day.

Revision ID: 5a9c1e3d7b24
Revises: 7c2e4f9a1b3d
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5a9c1e3d7b24"
down_revision: str | None = "7c2e4f9a1b3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A new table only: runs keep their usage on their steps.
    op.create_table(
        "usage_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("chat", "planner", name="usagekind", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_usage_events_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_events")),
    )
    op.create_index(
        op.f("ix_usage_events_created_at"), "usage_events", ["created_at"], unique=False
    )
    op.create_index(op.f("ix_usage_events_user_id"), "usage_events", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_usage_events_user_id"), table_name="usage_events")
    op.drop_index(op.f("ix_usage_events_created_at"), table_name="usage_events")
    op.drop_table("usage_events")
