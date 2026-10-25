"""Fixtures of the recorded-run tests of conditions and review loops: the real
background executor over a file database (one connection per thread), as in the app."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from api.db import Database
from api.models import Base, User
from api.repositories import users
from api.services.run_executor import BackgroundRunExecutor
from api.services.runs import RunService


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db = Database(f"sqlite:///{tmp_path / 'flow.sqlite3'}")
    Base.metadata.create_all(db.engine)
    yield db
    db.engine.dispose()


@pytest.fixture
def owner(database: Database) -> User:
    with database.session() as session:
        return users.create(session, "runner", "hash")


@pytest.fixture
def executor() -> Iterator[BackgroundRunExecutor]:
    background = BackgroundRunExecutor(max_concurrent=2, grace_seconds=2.0)
    yield background
    background.shutdown()


@pytest.fixture
def service(database: Database, executor: BackgroundRunExecutor) -> RunService:
    return RunService(database, executor, max_parallel_steps=4)
