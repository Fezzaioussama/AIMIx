"""add pipeline inputs and step expected output

Revision ID: 138f208b1292
Revises: 21980d98eac9
Create Date: 2026-10-18 23:02:37.974491
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "138f208b1292"
down_revision: str | None = "21980d98eac9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing pipelines keep running on one free-text input, and their steps
    # leave the expected output to the prompt, as before.
    with op.batch_alter_table("pipeline_steps", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("expected_output", sa.String(length=500), server_default="", nullable=False)
        )

    # A plain string default, never sa.text(): an expression default makes
    # Alembic rebuild the table on SQLite, and dropping the old `pipelines`
    # with foreign keys on would cascade-delete every pipeline step.
    with op.batch_alter_table("pipelines", schema=None) as batch_op:
        batch_op.add_column(sa.Column("inputs", sa.JSON(), server_default="[]", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("pipelines", schema=None) as batch_op:
        batch_op.drop_column("inputs")

    with op.batch_alter_table("pipeline_steps", schema=None) as batch_op:
        batch_op.drop_column("expected_output")
