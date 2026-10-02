"""add agent step role and tool policy

Revision ID: 8f9a46d0c5a6
Revises: 0001
Create Date: 2026-10-02 23:12:13.556053
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8f9a46d0c5a6"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing steps inherit the old all-tools behavior and an empty role.
    with op.batch_alter_table("pipeline_steps", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("role", sa.String(length=100), server_default="", nullable=False)
        )
        batch_op.add_column(sa.Column("allowed_tools", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("pipeline_steps", schema=None) as batch_op:
        batch_op.drop_column("allowed_tools")
        batch_op.drop_column("role")
