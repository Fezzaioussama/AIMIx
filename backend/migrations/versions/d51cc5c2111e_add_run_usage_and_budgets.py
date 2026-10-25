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
    # Plain ALTER TABLE, never a batch: on SQLite a batch rebuilds the table, and
    # dropping the old `runs` with foreign keys on would cascade-delete every run
    # step. Steps recorded before this revision used tokens nobody counted: they
    # start at zero with an unknown cost, and their runs have no limit.
    op.add_column(
        "run_steps",
        sa.Column("input_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "run_steps",
        sa.Column("output_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("run_steps", sa.Column("cost_usd", sa.Float(), nullable=True))
    op.add_column("runs", sa.Column("max_cost_usd", sa.Float(), nullable=True))
    op.add_column("runs", sa.Column("max_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    # Also in place (SQLite 3.35 or newer), so the runs and steps stay.
    op.drop_column("runs", "max_tokens")
    op.drop_column("runs", "max_cost_usd")
    op.drop_column("run_steps", "cost_usd")
    op.drop_column("run_steps", "output_tokens")
    op.drop_column("run_steps", "input_tokens")
