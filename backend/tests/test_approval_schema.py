"""The schema behind approval gates: the migration, the new status and cascades."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, func, select, text

from api.models import STATUS_MAX_LENGTH, ApprovalStatus, RunApproval, RunStatus
from api.repositories import runs
from tests.approval_fakes import (
    file_database,
    make_owner,
    make_pipeline,
    request_approval,
    running_run,
)
from tests.test_database import migration_config


def test_the_migration_keeps_every_saved_integration_asking_first(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'before_approvals.sqlite3'}"
    config = migration_config(url)
    command.upgrade(config, "d7613f758b22")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, username, password_hash, created_at, refresh_token_hash)"
                " VALUES (1, 'owner', 'hash', CURRENT_TIMESTAMP, '')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO integrations (id, user_id, name, url, headers_encrypted,"
                " header_hints, enabled, created_at) VALUES"
                " (1, 1, 'crm', 'https://crm.example/mcp', '', '[]', 1, CURRENT_TIMESTAMP)"
            )
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(url)
    with engine.connect() as connection:
        asking = connection.execute(text("SELECT require_approval FROM integrations")).scalar_one()
    engine.dispose()
    assert asking == 1


def test_every_status_fits_the_status_column() -> None:
    for statuses in (RunStatus, ApprovalStatus):
        assert max(len(status.value) for status in statuses) <= STATUS_MAX_LENGTH


def test_a_runs_requests_are_deleted_with_it(tmp_path: Path) -> None:
    database = file_database(tmp_path)
    owner = make_owner(database)
    run_id = running_run(database, owner, make_pipeline(database, owner))
    with database.session() as session:
        request_approval(session, run_id)
        request_approval(session, run_id, step=2)

    with database.session() as session:
        run = runs.load(session, run_id)
        assert run is not None
        runs.delete(session, run)

    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(RunApproval)) == 0
    database.engine.dispose()
