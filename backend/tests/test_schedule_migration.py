"""The schedules migration keeps every recorded run and step, in both directions.

On SQLite, adding a foreign key to `runs` rebuilds the table, and dropping the
old one with foreign keys on would cascade-delete every run step: these tests
migrate a database that already holds a run, the way production does."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from alembic import command
from sqlalchemy import text

from api.db import Database
from tests.test_database import migration_config

BEFORE = "d7613f758b22"


@pytest.fixture
def url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'runs.sqlite3'}"


def seed_a_finished_run(url: str) -> None:
    """A database as it was before schedules existed, holding one run and its step."""
    command.upgrade(migration_config(url), BEFORE)
    database = Database(url)
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, username, password_hash, refresh_token_hash, created_at) "
                "VALUES (1, 'owner', 'hash', '', CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO pipelines (id, name, user_id, created_at, inputs) "
                "VALUES (1, 'Digest', 1, CURRENT_TIMESTAMP, '[]')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO runs (id, user_id, pipeline_id, pipeline_name, definition, "
                "input_text, input_values, status, final_output, error_code, error_detail, "
                "created_at) VALUES (1, 1, 1, 'Digest', '{}', 'go', '{}', 'succeeded', "
                "'done', '', '', CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO run_steps (run_id, step_order, stage, title, model, status, "
                "is_output, input_used, output, tool_calls, error_code, error_detail) "
                "VALUES (1, 1, 1, 'Step', 'm', 'succeeded', 1, 'go', 'done', '[]', '', '')"
            )
        )
    database.engine.dispose()


def query(url: str, sql: str) -> list[Any]:
    database = Database(url)  # foreign keys on, as in the app
    with database.engine.connect() as connection:
        rows = list(connection.execute(text(sql)))
    database.engine.dispose()
    return rows


def run_columns(url: str) -> list[str]:
    return [row[1] for row in query(url, "PRAGMA table_info(runs)")]


def references(url: str, table: str) -> dict[str, str]:
    """Each foreign key column of ``table``, with the table it points to and its delete action."""
    rows = query(url, f"PRAGMA foreign_key_list({table})")
    return {row[3]: f"{row[2]} {row[6]}" for row in rows}


def test_upgrading_keeps_the_runs_and_steps_and_marks_old_runs_manual(url: str) -> None:
    seed_a_finished_run(url)

    command.upgrade(migration_config(url), "head")

    assert query(url, "SELECT count(*) FROM run_steps") == [(1,)]
    assert query(url, 'SELECT "trigger", schedule_id, final_output FROM runs') == [
        ("manual", None, "done")
    ]
    assert references(url, "runs")["schedule_id"] == "schedules SET NULL"
    assert references(url, "run_steps") == {"run_id": "runs CASCADE"}
    # The rebuilt table still carries its other foreign keys.
    assert references(url, "runs")["pipeline_id"] == "pipelines SET NULL"
    assert references(url, "runs")["user_id"] == "users CASCADE"


def test_the_foreign_keys_still_act_after_upgrading(url: str) -> None:
    seed_a_finished_run(url)
    command.upgrade(migration_config(url), "head")
    database = Database(url)
    try:
        with database.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO schedules (id, user_id, pipeline_id, frequency, hour, minute, "
                    "timezone, input_text, input_values, enabled, last_error, created_at) "
                    "VALUES (1, 1, 1, 'daily', 9, 0, 'UTC', 'go', '{}', 1, '', CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(text("UPDATE runs SET schedule_id = 1, \"trigger\" = 'schedule'"))
        with database.engine.begin() as connection:
            connection.execute(text("DELETE FROM schedules"))
        with database.engine.connect() as connection:
            kept = connection.execute(text('SELECT "trigger", schedule_id FROM runs')).all()
    finally:
        database.engine.dispose()

    assert [tuple(row) for row in kept] == [("schedule", None)]  # the run stays, unlinked


def test_downgrading_keeps_the_runs_and_steps_and_removes_what_schedules_added(url: str) -> None:
    seed_a_finished_run(url)
    config = migration_config(url)
    command.upgrade(config, "head")

    command.downgrade(config, BEFORE)

    assert query(url, "SELECT count(*) FROM run_steps") == [(1,)]
    assert query(url, "SELECT final_output FROM runs") == [("done",)]
    assert "trigger" not in run_columns(url)
    assert "schedule_id" not in run_columns(url)
    assert "schedule_id" not in references(url, "runs")
    assert query(url, "SELECT name FROM sqlite_master WHERE name = 'schedules'") == []
    command.upgrade(config, "head")  # and it can be applied again
    assert query(url, "SELECT count(*) FROM run_steps") == [(1,)]
