"""Add cross-process authentication rate limiting.

Revision ID: e402a8ff19d7
Revises: c61c8c31de21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e402a8ff19d7"
down_revision: str | None = "c61c8c31de21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_buckets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("identity_hash", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rate_limit_buckets")),
        sa.UniqueConstraint("identity_hash", "action", name="uq_rate_limit_key"),
    )


def downgrade() -> None:
    op.drop_table("rate_limit_buckets")
