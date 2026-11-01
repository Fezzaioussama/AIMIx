"""Add deliveries: where a pipeline's results are posted when one of its runs ends.

Revision ID: 463d9d894942
Revises: c4834c6c5886
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "463d9d894942"
down_revision: str | None = "c4834c6c5886"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A new table only; nothing is sent for a delivery until its owner confirms it.
    op.create_table(
        "deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("pipeline_id", sa.Integer(), nullable=False),
        sa.Column("url_encrypted", sa.Text(), nullable=False),
        sa.Column("host", sa.String(length=253), nullable=False),
        sa.Column("hint", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["pipeline_id"],
            ["pipelines.id"],
            name=op.f("fk_deliveries_pipeline_id_pipelines"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_deliveries_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deliveries")),
        sa.UniqueConstraint("pipeline_id", name=op.f("uq_deliveries_pipeline_id")),
    )
    op.create_index(op.f("ix_deliveries_user_id"), "deliveries", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_deliveries_user_id"), table_name="deliveries")
    op.drop_table("deliveries")
