"""Add the schedules' claimed occurrence: the one a tick claimed and has not settled
yet, so a restart can start an occurrence the process died on.

Revision ID: ab6587d1d481
Revises: 463d9d894942
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ab6587d1d481"
down_revision: str | None = "463d9d894942"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable, so every existing schedule holds no claim.
    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.add_column(sa.Column("claimed_occurrence", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.drop_column("claimed_occurrence")
