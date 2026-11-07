"""Add run shares: a secret link that shows one run's report to anyone who has it.

Revision ID: d4e7a1b2c9f3
Revises: c7d1f3a9e5b2
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e7a1b2c9f3"
down_revision: str | None = "c7d1f3a9e5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A new table only; no existing row changes.
    op.create_table(
        "run_shares",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name=op.f("fk_run_shares_run_id_runs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_run_shares")),
        sa.UniqueConstraint("run_id", name=op.f("uq_run_shares_run_id")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_run_shares_token_hash")),
    )


def downgrade() -> None:
    op.drop_table("run_shares")
