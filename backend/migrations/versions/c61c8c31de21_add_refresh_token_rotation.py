"""Add refresh-token rotation state.

Revision ID: c61c8c31de21
Revises: 138f208b1292
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c61c8c31de21"
down_revision: str | None = "138f208b1292"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("users", "refresh_token_hash")
