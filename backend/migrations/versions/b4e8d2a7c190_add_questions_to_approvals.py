"""Add what a request at the approval gate asks (a tool call's OK, or a question an
agent asked with ask_user) and the person's answer to a question.

Revision ID: b4e8d2a7c190
Revises: 5a9c1e3d7b24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4e8d2a7c190"
down_revision: str | None = "5a9c1e3d7b24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain ALTER TABLE, never a batch (a rebuild would cascade on SQLite). Every
    # request so far is a tool call's OK, with no answer.
    op.add_column(
        "run_approvals",
        sa.Column(
            "kind",
            sa.Enum("approval", "question", name="approvalkind", native_enum=False, length=16),
            server_default="approval",
            nullable=False,
        ),
    )
    op.add_column(
        "run_approvals", sa.Column("answer", sa.Text(), server_default="", nullable=False)
    )


def downgrade() -> None:
    # Also in place (SQLite 3.35 or newer), so the rows stay.
    op.drop_column("run_approvals", "answer")
    op.drop_column("run_approvals", "kind")
