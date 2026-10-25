"""The migration for conditions, review loops and rounds keeps every pipeline, run,
step and approval, in both directions.

On SQLite a batch rebuild of `run_steps` or `pipeline_steps` would cascade-delete
their children while foreign keys are on: these tests migrate a database that
already holds them, the way production does."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from alembic import command
from sqlalchemy import text

from api.db import Database
from tests.test_database import migration_config

BEFORE = "086b460e2361"


@pytest.fixture
def url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'flow.sqlite3'}"


def run_sql(url: str, *statements: str) -> None:
    database = Database(url)  # foreign keys on, as in the app
    with database.engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
    database.engine.dispose()


def query(url: str, sql: str) -> list[Any]:
    database = Database(url)
    with database.engine.connect() as connection:
        rows = [tuple(row) for row in connection.execute(text(sql))]
    database.engine.dispose()
    return rows


def columns(url: str, table: str) -> list[str]:
    return [row[1] for row in query(url, f"PRAGMA table_info({table})")]


def seed_a_pipeline_and_its_runs(url: str) -> None:
    """A database as it was before this revision: a pipeline, a finished run, its
    steps, and an approval of the run."""
    command.upgrade(migration_config(url), BEFORE)
    run_sql(
        url,
        "INSERT INTO users (id, username, password_hash, refresh_token_hash, created_at) "
        "VALUES (1, 'owner', 'hash', '', CURRENT_TIMESTAMP)",
        "INSERT INTO pipelines (id, name, user_id, created_at, inputs) "
        "VALUES (1, 'Digest', 1, CURRENT_TIMESTAMP, '[]')",
        'INSERT INTO pipeline_steps (id, pipeline_id, "order", stage, title, role, '
        "allowed_tools, is_output, expected_output, prompt, model) VALUES "
        "(1, 1, 1, 1, 'Research', '', NULL, 0, '', 'p1 {input}', 'm'), "
        "(2, 1, 2, 2, 'Write', '', NULL, 1, '', 'p2 {input}', 'm')",
        "INSERT INTO runs (id, user_id, pipeline_id, pipeline_name, definition, input_text, "
        "input_values, status, final_output, error_code, error_detail, created_at, "
        "\"trigger\") VALUES (1, 1, 1, 'Digest', '{}', 'go', '{}', 'succeeded', 'done', '', "
        "'', CURRENT_TIMESTAMP, 'manual')",
        "INSERT INTO run_steps (id, run_id, step_order, stage, title, model, status, "
        "is_output, input_used, output, tool_calls, error_code, error_detail, input_tokens, "
        "output_tokens) VALUES (1, 1, 1, 1, 'Research', 'm', 'succeeded', 0, 'go', 'facts', "
        "'[]', '', '', 10, 5), (2, 1, 2, 2, 'Write', 'm', 'succeeded', 1, 'facts', 'draft', "
        "'[]', '', '', 20, 8)",
        "INSERT INTO run_approvals (id, run_id, step_order, tool_name, tool_source, "
        "tool_description, arguments, arguments_truncated, status, created_at, expires_at) "
        "VALUES (1, 1, 2, 'crm_send_email', 'crm', 'Send.', '{}', 0, 'approved', "
        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
    )


def counts(url: str) -> list[tuple[str, int]]:
    tables = ("pipelines", "pipeline_steps", "runs", "run_steps", "run_approvals")
    return [(table, query(url, f"SELECT count(*) FROM {table}")[0][0]) for table in tables]


def test_upgrading_keeps_everything_and_gives_old_rows_the_defaults(url: str) -> None:
    seed_a_pipeline_and_its_runs(url)
    before = counts(url)

    command.upgrade(migration_config(url), "head")

    assert (
        counts(url)
        == before
        == [
            ("pipelines", 1),
            ("pipeline_steps", 2),
            ("runs", 1),
            ("run_steps", 2),
            ("run_approvals", 1),
        ]
    )
    # No step had a condition or a review; every recorded step went through round 1.
    assert query(url, "SELECT condition, review FROM pipeline_steps ORDER BY id") == [
        (None, None),
        (None, None),
    ]
    assert query(url, "SELECT rounds, verdict, input_tokens FROM run_steps ORDER BY id") == [
        (1, None, 10),
        (1, None, 20),
    ]
    assert query(url, "SELECT output FROM run_steps ORDER BY id") == [("facts",), ("draft",)]


def test_the_new_columns_hold_what_the_engine_writes(url: str) -> None:
    seed_a_pipeline_and_its_runs(url)
    command.upgrade(migration_config(url), "head")

    run_sql(
        url,
        'UPDATE pipeline_steps SET condition = \'{"source": "step:1", "operator": '
        '"contains", "value": "x"}\' WHERE id = 1',
        'UPDATE pipeline_steps SET review = \'{"send_back_to_stage": 1, "max_rounds": 2}\' '
        "WHERE id = 2",
        "UPDATE run_steps SET rounds = 3, verdict = 'revise' WHERE id = 2",
        "UPDATE run_steps SET status = 'skipped' WHERE id = 1",
    )

    assert query(url, "SELECT status, rounds, verdict FROM run_steps ORDER BY id") == [
        ("skipped", 1, None),
        ("succeeded", 3, "revise"),
    ]


def test_downgrading_keeps_the_runs_and_steps_and_removes_what_this_added(url: str) -> None:
    seed_a_pipeline_and_its_runs(url)
    config = migration_config(url)
    command.upgrade(config, "head")
    run_sql(url, "UPDATE run_steps SET status = 'skipped', rounds = 2 WHERE id = 1")

    command.downgrade(config, BEFORE)

    assert counts(url) == [
        ("pipelines", 1),
        ("pipeline_steps", 2),
        ("runs", 1),
        ("run_steps", 2),
        ("run_approvals", 1),
    ]
    assert "rounds" not in columns(url, "run_steps")
    assert "verdict" not in columns(url, "run_steps")
    assert "condition" not in columns(url, "pipeline_steps")
    assert "review" not in columns(url, "pipeline_steps")
    # The older code does not know `skipped`: that step reads as a finished one.
    assert query(url, "SELECT status, output FROM run_steps ORDER BY id") == [
        ("succeeded", "facts"),
        ("succeeded", "draft"),
    ]
    command.upgrade(config, "head")  # and it can be applied again
    assert query(url, "SELECT count(*) FROM run_steps") == [(2,)]


def test_the_foreign_keys_still_act_after_upgrading(url: str) -> None:
    seed_a_pipeline_and_its_runs(url)
    command.upgrade(migration_config(url), "head")

    run_sql(url, "DELETE FROM runs WHERE id = 1")

    # Deleting a run still deletes its steps and approvals (cascade), and nothing else.
    assert query(url, "SELECT count(*) FROM run_steps") == [(0,)]
    assert query(url, "SELECT count(*) FROM run_approvals") == [(0,)]
    assert query(url, "SELECT count(*) FROM pipeline_steps") == [(2,)]
