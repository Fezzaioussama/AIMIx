"""Add each person's standing instructions (Settings → Memory): what every chat, plan
and run is told to keep in mind, one row per account.

Revision ID: d1eb2d007f66
Revises: 5d2d657b29e7
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1eb2d007f66"
down_revision: str | None = "5d2d657b29e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_memory",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_memory_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_memory")),
        sa.UniqueConstraint("user_id", name=op.f("uq_user_memory_user_id")),
    )


def downgrade() -> None:
    op.drop_table("user_memory")
