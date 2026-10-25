"""Add each user's access-token version and each schedule's spending limits.

Revision ID: ee34d4ea46e9
Revises: bcef76dc923f
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ee34d4ea46e9"
down_revision: str | None = "bcef76dc923f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain ALTER TABLE, never a batch: on SQLite a batch rebuilds the table, and
    # dropping the old one with foreign keys on would cascade-delete its children.
    # Tokens issued before this revision carry no version and count as version 0.
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    # Existing schedules keep starting runs with the server's default limits.
    op.add_column("schedules", sa.Column("max_cost_usd", sa.Float(), nullable=True))
    op.add_column("schedules", sa.Column("max_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    # Also in place (SQLite 3.35 or newer), so the rows stay.
    op.drop_column("schedules", "max_tokens")
    op.drop_column("schedules", "max_cost_usd")
    op.drop_column("users", "token_version")
