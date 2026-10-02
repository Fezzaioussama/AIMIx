"""Schema migrations and the one-off import from the Django database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from api.exceptions import ValidationFailed
from api.models import Base, Pipeline
from api.repositories.legacy_import import import_django_database
from tests.test_security import DJANGO_HASH, DJANGO_PASSWORD

BACKEND_DIR = Path(__file__).resolve().parents[1]


def migration_config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["configure_logger"] = False
    return config


def test_migrations_build_exactly_the_models_schema(tmp_path: Path) -> None:
    """Like `makemigrations --check`: a model change without a migration fails here."""
    url = f"sqlite:///{tmp_path / 'migrated.sqlite3'}"
    config = migration_config(url)
    command.upgrade(config, "head")

    engine = create_engine(url)
    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    engine.dispose()
    assert differences == []


def test_agent_step_migration_preserves_old_pipeline_steps(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'old.sqlite3'}"
    config = migration_config(url)
    command.upgrade(config, "0001")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users VALUES (1, 'owner', 'hash', CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO pipelines VALUES (1, 'Old', 1, CURRENT_TIMESTAMP)"))
        connection.execute(
            text(
                "INSERT INTO pipeline_steps VALUES "
                "(1, 1, 1, 1, 'Step', 1, 'Do {input}', 'model/id')"
            )
        )
    engine.dispose()
    command.upgrade(config, "head")
    engine = create_engine(url)
    with engine.connect() as connection:
        role, allowed = connection.execute(
            text("SELECT role, allowed_tools FROM pipeline_steps WHERE id = 1")
        ).one()
    engine.dispose()
    assert (role, allowed) == ("", None)


def legacy_database(path: Path, *, with_stage_columns: bool = True) -> Path:
    """A minimal copy of the Django schema, holding one account and pipeline."""
    extra = ", stage integer, title varchar(100), is_output bool" if with_stage_columns else ""
    with sqlite3.connect(path) as db:
        db.executescript(
            f"""
            CREATE TABLE auth_user (id integer primary key, username varchar(150),
                password varchar(128), date_joined datetime);
            CREATE TABLE api_pipeline (id integer primary key, name varchar(255),
                user_id integer, created_at datetime);
            CREATE TABLE api_pipelinestep (id integer primary key, pipeline_id integer,
                "order" integer, prompt text, model varchar(200){extra});
            """
        )
        db.execute(
            "INSERT INTO auth_user VALUES (4, 'legacy', ?, '2026-09-27 17:17:07')", [DJANGO_HASH]
        )
        db.execute("INSERT INTO api_pipeline VALUES (9, 'Old', 4, '2026-09-27 17:20:55.229686')")
        if with_stage_columns:
            db.execute(
                "INSERT INTO api_pipelinestep VALUES (21, 9, 1, 'p {input}', 'vendor/m', 1, 'T', 1)"
            )
        else:
            db.execute("INSERT INTO api_pipelinestep VALUES (21, 9, 2, 'p {input}', 'vendor/m')")
    return path


def test_the_import_keeps_ids_and_passwords(
    tmp_path: Path, session: Session, client: TestClient
) -> None:
    summary = import_django_database(session, legacy_database(tmp_path / "old.sqlite3"))

    assert (summary.users, summary.pipelines, summary.steps) == (1, 1, 1)
    pipeline = session.get(Pipeline, 9)
    assert pipeline is not None and pipeline.user_id == 4
    assert (pipeline.steps[0].title, pipeline.steps[0].is_output) == ("T", True)
    login = client.post("/api/login", json={"username": "legacy", "password": DJANGO_PASSWORD})
    assert login.status_code == 200


def test_the_import_defaults_columns_an_older_schema_lacks(
    tmp_path: Path, session: Session
) -> None:
    import_django_database(
        session, legacy_database(tmp_path / "old.sqlite3", with_stage_columns=False)
    )
    step = session.get(Pipeline, 9).steps[0]  # type: ignore[union-attr]
    assert (step.stage, step.title, step.is_output) == (2, "", False)


def test_the_import_refuses_to_run_twice(tmp_path: Path, session: Session) -> None:
    legacy = legacy_database(tmp_path / "old.sqlite3")
    import_django_database(session, legacy)
    with pytest.raises(ValidationFailed, match="already has accounts"):
        import_django_database(session, legacy)


def test_the_import_reports_a_missing_file(tmp_path: Path, session: Session) -> None:
    with pytest.raises(ValidationFailed, match="does not exist"):
        import_django_database(session, tmp_path / "absent.sqlite3")
