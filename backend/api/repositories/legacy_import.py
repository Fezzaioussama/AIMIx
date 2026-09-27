"""One-off copy of accounts and pipelines from the previous Django database.

Reads the old SQLite file read-only and writes the rows into this app's
database in one transaction, keeping ids and password hashes (the hash format
is unchanged, so every account keeps its password). Refuses to run against a
database that already has accounts, so running it twice cannot duplicate data.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from api.exceptions import ValidationFailed
from api.models import Pipeline, PipelineStep, User


@dataclass(frozen=True)
class ImportSummary:
    users: int
    pipelines: int
    steps: int


def import_django_database(session: Session, legacy_file: Path) -> ImportSummary:
    if session.scalar(select(exists().where(User.id.is_not(None)))):
        raise ValidationFailed("This database already has accounts; import into an empty one.")
    if not legacy_file.is_file():
        raise ValidationFailed(f"{legacy_file} does not exist.")

    with sqlite3.connect(f"file:{legacy_file}?mode=ro", uri=True) as legacy:
        users = [_user(row) for row in legacy.execute(USERS_SQL)]
        pipelines = [_pipeline(row) for row in legacy.execute(PIPELINES_SQL)]
        steps = [_step(row) for row in legacy.execute(_steps_sql(legacy))]

    session.add_all([*users, *pipelines, *steps])
    session.commit()
    return ImportSummary(users=len(users), pipelines=len(pipelines), steps=len(steps))


USERS_SQL = "SELECT id, username, password, date_joined FROM auth_user"
PIPELINES_SQL = "SELECT id, name, user_id, created_at FROM api_pipeline"


def _steps_sql(legacy: sqlite3.Connection) -> str:
    """Older Django schemas predate stage/title/is_output; default them."""
    columns = {row[1] for row in legacy.execute("PRAGMA table_info(api_pipelinestep)")}
    stage = "stage" if "stage" in columns else '"order"'
    title = "title" if "title" in columns else "''"
    is_output = "is_output" if "is_output" in columns else "0"
    return (
        f'SELECT id, pipeline_id, "order", {stage}, {title}, {is_output}, prompt, model '
        "FROM api_pipelinestep"
    )


def _timestamp(value: str) -> datetime:
    # Django stored naive UTC timestamps in SQLite.
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _user(row: tuple) -> User:
    user_id, username, password_hash, joined = row
    return User(
        id=user_id, username=username, password_hash=password_hash, created_at=_timestamp(joined)
    )


def _pipeline(row: tuple) -> Pipeline:
    pipeline_id, name, user_id, created = row
    return Pipeline(id=pipeline_id, name=name, user_id=user_id, created_at=_timestamp(created))


def _step(row: tuple) -> PipelineStep:
    step_id, pipeline_id, order, stage, title, is_output, prompt, model = row
    return PipelineStep(
        id=step_id,
        pipeline_id=pipeline_id,
        order=order,
        stage=stage,
        title=title,
        is_output=bool(is_output),
        prompt=prompt,
        model=model,
    )
