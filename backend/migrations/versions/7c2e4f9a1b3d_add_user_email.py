"""Add the accounts' email address and their notification switch: where password-reset
links and notifications go.

Revision ID: 7c2e4f9a1b3d
Revises: ab6587d1d481
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c2e4f9a1b3d"
down_revision: str | None = "ab6587d1d481"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain ALTER TABLE and an index, never a batch: on SQLite a batch rebuilds the
    # table, and dropping the old `users` with foreign keys on would cascade-delete
    # everything the accounts own. No account has an address yet; notifications
    # are on once one is given.
    op.add_column("users", sa.Column("email", sa.String(length=254), nullable=True))
    op.add_column(
        "users",
        sa.Column("email_notifications", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)


def downgrade() -> None:
    # Also in place (SQLite 3.35 or newer), so the rows stay.
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_column("users", "email_notifications")
    op.drop_column("users", "email")
