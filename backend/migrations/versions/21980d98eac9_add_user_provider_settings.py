"""add user provider settings

Revision ID: 21980d98eac9
Revises: 8f9a46d0c5a6
Create Date: 2026-10-18 13:33:02.573515
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "21980d98eac9"
down_revision: str | None = "8f9a46d0c5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("api_key_hint", sa.String(length=4), nullable=False),
        sa.Column("default_model", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_provider_settings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_settings")),
        sa.UniqueConstraint("user_id", "provider", name="uq_provider_setting_per_user"),
    )
    with op.batch_alter_table("provider_settings", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_provider_settings_user_id"), ["user_id"], unique=False)

    # Existing accounts keep using LLM_PROVIDER until they choose one.
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("llm_provider", sa.String(length=50), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("llm_provider")

    with op.batch_alter_table("provider_settings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_provider_settings_user_id"))

    op.drop_table("provider_settings")
