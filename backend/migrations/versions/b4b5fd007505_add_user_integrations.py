"""Add users' own MCP servers (Settings page → Integrations).

Revision ID: b4b5fd007505
Revises: e402a8ff19d7
Create Date: 2026-10-24 21:52:46.135453
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4b5fd007505"
down_revision: str | None = "e402a8ff19d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=31), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("headers_encrypted", sa.Text(), nullable=False),
        sa.Column("header_hints", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_integrations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integrations")),
        sa.UniqueConstraint("user_id", "name", name="uq_integration_name_per_user"),
    )
    with op.batch_alter_table("integrations", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_integrations_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("integrations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_integrations_user_id"))

    op.drop_table("integrations")
