"""Add each run step's token usage and cost, and each run's spending limits.

Revision ID: d51cc5c2111e
Revises: d7613f758b22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d51cc5c2111e"
down_revision: str | None = "d7613f758b22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Steps recorded before this revision used tokens nobody counted: they start
    # at zero, with an unknown cost; their runs have no limit.
    with op.batch_alter_table("run_steps", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(sa.Column("cost_usd", sa.Float(), nullable=True))

    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("max_cost_usd", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("max_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_column("max_tokens")
        batch_op.drop_column("max_cost_usd")

    with op.batch_alter_table("run_steps", schema=None) as batch_op:
        batch_op.drop_column("cost_usd")
        batch_op.drop_column("output_tokens")
        batch_op.drop_column("input_tokens")
