"""Add what a run's owner thought of it: a rating and a note the planner learns from.

Revision ID: c7d1f3a9e5b2
Revises: b4e8d2a7c190
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7d1f3a9e5b2"
down_revision: str | None = "b4e8d2a7c190"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain ALTER TABLE, never a batch (a rebuild would cascade on SQLite). No run so
    # far has been rated or annotated.
    op.add_column("runs", sa.Column("rating", sa.Integer(), nullable=True))
    op.add_column("runs", sa.Column("feedback", sa.Text(), server_default="", nullable=False))


def downgrade() -> None:
    # Also in place (SQLite 3.35 or newer), so the rows stay.
    op.drop_column("runs", "feedback")
    op.drop_column("runs", "rating")
