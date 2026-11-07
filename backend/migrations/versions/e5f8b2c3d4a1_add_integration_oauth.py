"""Add an integration's OAuth sign-in: its status, what it keeps sealed (the attempt,
then the tokens) and the state its call back is found by.

Revision ID: e5f8b2c3d4a1
Revises: d4e7a1b2c9f3
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f8b2c3d4a1"
down_revision: str | None = "d4e7a1b2c9f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain ALTER TABLE, never a batch (a rebuild would cascade on SQLite). No
    # integration so far has signed in.
    op.add_column(
        "integrations",
        sa.Column("oauth_status", sa.String(length=16), server_default="", nullable=False),
    )
    op.add_column(
        "integrations", sa.Column("oauth_encrypted", sa.Text(), server_default="", nullable=False)
    )
    op.add_column(
        "integrations", sa.Column("oauth_state_hash", sa.String(length=64), nullable=True)
    )
    op.create_index(
        op.f("ix_integrations_oauth_state_hash"), "integrations", ["oauth_state_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_integrations_oauth_state_hash"), table_name="integrations")
    op.drop_column("integrations", "oauth_state_hash")
    op.drop_column("integrations", "oauth_encrypted")
    op.drop_column("integrations", "oauth_status")
