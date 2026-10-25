"""Add schedules, and mark what started each run.

Revision ID: 086b460e2361
Revises: d7613f758b22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "086b460e2361"
down_revision: str | None = "d7613f758b22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FREQUENCIES = ("hourly", "daily", "weekdays", "weekly", "monthly")
TRIGGERS = ("manual", "schedule", "chat")


def _choice(name: str, values: tuple[str, ...]) -> sa.Enum:
    # A plain VARCHAR(16): no native enum type and no CHECK constraint.
    return sa.Enum(*values, name=name, native_enum=False, length=16)


def _keep_run_steps() -> None:
    """SQLite cannot add or drop a foreign key in place, so `runs` is rebuilt,
    which drops the old table: with foreign keys on, that would cascade-delete
    every run step. They are switched off for this connection, which is closed
    after the migration. A pragma only applies outside a transaction, so this
    comes before any other statement of the revision."""
    if op.get_bind().dialect.name == "sqlite":
        op.execute("PRAGMA foreign_keys=OFF")


def _create_schedules() -> None:
    op.create_table(
        "schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("pipeline_id", sa.Integer(), nullable=False),
        sa.Column("frequency", _choice("schedulefrequency", FREQUENCIES), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
        sa.Column("minute", sa.Integer(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("day_of_month", sa.Integer(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("input_values", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["pipeline_id"],
            ["pipelines.id"],
            name=op.f("fk_schedules_pipeline_id_pipelines"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_schedules_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schedules")),
    )
    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_schedules_next_run_at"), ["next_run_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_schedules_pipeline_id"), ["pipeline_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_schedules_user_id"), ["user_id"], unique=False)


def _mark_runs() -> None:
    # Runs recorded before this revision were started by hand or from chat;
    # they all count as "manual".
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "trigger", _choice("runtrigger", TRIGGERS), server_default="manual", nullable=False
            )
        )
        batch_op.add_column(sa.Column("schedule_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_runs_schedule_id"), ["schedule_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_runs_schedule_id_schedules"),
            "schedules",
            ["schedule_id"],
            ["id"],
            ondelete="SET NULL",
        )


def upgrade() -> None:
    _keep_run_steps()
    _create_schedules()
    _mark_runs()


def downgrade() -> None:
    _keep_run_steps()
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_runs_schedule_id_schedules"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_runs_schedule_id"))
        batch_op.drop_column("schedule_id")
        batch_op.drop_column("trigger")

    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_schedules_user_id"))
        batch_op.drop_index(batch_op.f("ix_schedules_pipeline_id"))
        batch_op.drop_index(batch_op.f("ix_schedules_next_run_at"))

    op.drop_table("schedules")
