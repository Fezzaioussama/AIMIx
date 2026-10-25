"""Stopping a run and resuming it at once: the stopped attempt may take a while
to wind down (a tool call it cannot abandon), and must never record its end
over the attempt that replaces it."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from api.db import Database
from api.exceptions import Conflict
from api.models import Base, RunStatus, User
from api.repositories import users
from api.services.agent_types import AgentOutcome, AgentTask
from api.services.run_executor import BackgroundRunExecutor
from api.services.runs import RunService, RunStart
from tests.test_runs_service import ScriptedAgent
from tests.usage_fakes import WAIT_SECONDS, load_run, staged_pipeline, wait_for_run


class SlowToStop:
    """Holds its step until stopped, then takes until ``let_go`` is set to end."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.let_go = threading.Event()

    async def execute(self, task: AgentTask) -> AgentOutcome:
        self.started.set()
        try:
            while True:
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            while not self.let_go.is_set():
                await asyncio.sleep(0.01)
            raise


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db = Database(f"sqlite:///{tmp_path / 'resume.sqlite3'}")
    Base.metadata.create_all(db.engine)
    yield db
    db.engine.dispose()


@pytest.fixture
def owner(database: Database) -> User:
    with database.session() as session:
        return users.create(session, "runner", "hash")


@pytest.fixture
def executor() -> Iterator[BackgroundRunExecutor]:
    # A resume waits this long for a stopped attempt to wind down before refusing.
    background = BackgroundRunExecutor(max_concurrent=2, grace_seconds=0.2)
    yield background
    background.shutdown()


def test_a_run_cannot_resume_while_its_stopped_attempt_winds_down(
    database: Database, owner: User, executor: BackgroundRunExecutor
) -> None:
    service = RunService(database, executor, max_parallel_steps=4)
    slow = SlowToStop()
    run = service.start(owner, staged_pipeline(database, owner, [1]), RunStart("x"), slow).run
    assert slow.started.wait(WAIT_SECONDS)

    assert service.cancel(owner, run.id).status == RunStatus.CANCELLED
    assert not executor.settled(run.id)
    with pytest.raises(Conflict, match="still stopping"):
        service.resume(owner, run.id, ScriptedAgent())
    assert load_run(database, run.id).status == RunStatus.CANCELLED

    slow.let_go.set()
    service.resume(owner, run.id, ScriptedAgent())  # waits the moment the wind-down takes

    # The old attempt's wind-down is over: nothing marks the new one interrupted.
    resumed = wait_for_run(database, run.id, lambda again: again.status == RunStatus.SUCCEEDED)
    assert resumed.final_output == "out-role-1"


def test_the_executor_knows_a_job_until_it_has_ended(executor: BackgroundRunExecutor) -> None:
    release = threading.Event()

    async def job() -> str:
        while not release.is_set():
            await asyncio.sleep(0.01)
        return "done"

    assert executor.settled(7)
    finished = executor.submit(7, job)
    assert not executor.settled(7)  # after waiting its grace for the job

    release.set()
    assert executor.settled(7)
    assert finished.result(timeout=0) == "done"
