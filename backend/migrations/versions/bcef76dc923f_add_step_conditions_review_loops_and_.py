"""Add conditional steps, review loops and the rounds a run step went through.

Revision ID: bcef76dc923f
Revises: 086b460e2361
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bcef76dc923f"
down_revision: str | None = "086b460e2361"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain ALTER TABLE, never a batch: on SQLite a batch rebuilds the table, and
    # dropping the old `run_steps` or `pipeline_steps` with foreign keys on would
    # cascade-delete their rows. Existing steps have no condition and no review,
    # and every step already recorded went through round 1 and gave no verdict
    # (the `skipped` status needs nothing: statuses are plain VARCHAR(16), no CHECK).
    op.add_column("pipeline_steps", sa.Column("condition", sa.JSON(), nullable=True))
    op.add_column("pipeline_steps", sa.Column("review", sa.JSON(), nullable=True))
    op.add_column(
        "run_steps",
        sa.Column("rounds", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column("run_steps", sa.Column("verdict", sa.String(length=16), nullable=True))


def downgrade() -> None:
    # Also in place (SQLite 3.35 or newer), so the pipelines, runs and steps stay.
    # The older code does not know `skipped`: such a step becomes a finished one
    # with no output, which a resumed run keeps just the same.
    op.execute("UPDATE run_steps SET status = 'succeeded' WHERE status = 'skipped'")
    op.drop_column("run_steps", "verdict")
    op.drop_column("run_steps", "rounds")
    op.drop_column("pipeline_steps", "review")
    op.drop_column("pipeline_steps", "condition")
