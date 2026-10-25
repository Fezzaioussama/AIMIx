"""How many runs one account may have active (RUN_MAX_ACTIVE_PER_USER), checked
inside the write that makes a run active, on every path that starts or resumes
one; and how long a caller waiting for a run's end waits (RUN_WAIT_MAX_SECONDS)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.db import Database
from api.deps import app_settings, run_executor
from api.exceptions import RunStillRunning, TooManyRuns
from api.models import Base, Pipeline, Run, RunStatus, User
from api.repositories import users
from api.services.run_executor import BackgroundRunExecutor
from api.services.run_policy import RunPolicy
from api.services.runs import RunService, RunStart
from tests.conftest import TEST_SETTINGS
from tests.test_endpoints import make_pipeline
from tests.test_runs_service import ParkedExecutor, ScriptedAgent
from tests.usage_fakes import load_run, staged_pipeline


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db = Database(f"sqlite:///{tmp_path / 'admission.sqlite3'}")
    Base.metadata.create_all(db.engine)
    yield db
    db.engine.dispose()


def account(database: Database, name: str) -> User:
    with database.session() as session:
        return users.create(session, name, "hash")


def parked(database: Database, cap: int) -> RunService:
    """Runs are saved queued and stay so: every one counts as active."""
    return RunService(database, ParkedExecutor(), 4, RunPolicy(max_active_per_user=cap))


def saved_runs(database: Database, owner: User) -> list[Run]:
    with database.session() as session:
        return list(session.query(Run).filter(Run.user_id == owner.id).order_by(Run.id))


def test_an_account_cannot_have_more_active_runs_than_its_cap(database: Database) -> None:
    owner, other = account(database, "owner"), account(database, "other")
    service = parked(database, cap=2)
    pipeline = staged_pipeline(database, owner, [1])
    for text in ("one", "two"):
        service.start(owner, pipeline, RunStart(text), ScriptedAgent())

    with pytest.raises(TooManyRuns) as refused:
        service.start(owner, pipeline, RunStart("three"), ScriptedAgent())

    assert (refused.value.code, refused.value.status_code) == ("too_many_runs", 429)
    assert "You already have 2 runs queued, running or waiting" in refused.value.detail
    assert [run.input_text for run in saved_runs(database, owner)] == ["one", "two"]
    # The cap is per account, and a run that ended frees its place.
    service.start(other, staged_pipeline(database, other, [1]), RunStart("x"), ScriptedAgent())
    first = saved_runs(database, owner)[0]
    service.cancel(owner, first.id)
    service.start(owner, pipeline, RunStart("four"), ScriptedAgent())


def test_a_resume_needs_room_too_and_changes_nothing_when_refused(database: Database) -> None:
    owner = account(database, "owner")
    service = parked(database, cap=1)
    pipeline = staged_pipeline(database, owner, [1])
    stopped = service.start(owner, pipeline, RunStart("one"), ScriptedAgent()).run
    service.cancel(owner, stopped.id)
    service.start(owner, pipeline, RunStart("two"), ScriptedAgent())

    with pytest.raises(TooManyRuns):
        service.resume(owner, stopped.id, ScriptedAgent())

    assert load_run(database, stopped.id).status == RunStatus.CANCELLED


def test_starts_at_the_same_moment_cannot_pass_the_cap_together(database: Database) -> None:
    owner = account(database, "owner")
    service = parked(database, cap=2)
    pipeline = staged_pipeline(database, owner, [1])
    gate = threading.Barrier(6)
    outcomes: list[str] = []

    def start(text: str) -> None:
        gate.wait()
        try:
            service.start(owner, pipeline, RunStart(text), ScriptedAgent())
            outcomes.append("started")
        except TooManyRuns:
            outcomes.append("refused")

    threads = [threading.Thread(target=start, args=(f"run-{n}",)) for n in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["refused"] * 4 + ["started"] * 2
    assert len(saved_runs(database, owner)) == 2


def test_starting_over_the_cap_is_a_429_with_the_standard_shape(
    app: FastAPI, auth_client: TestClient, session: Session, user: User
) -> None:
    app.dependency_overrides[run_executor] = ParkedExecutor
    app.dependency_overrides[app_settings] = lambda: TEST_SETTINGS.model_copy(
        update={"run_max_active_per_user": 1}
    )
    pipeline = make_pipeline(session, user, "Busy")
    url = f"/api/pipelines/{pipeline.id}/runs"

    assert auth_client.post(url, json={"input": "one"}).status_code == 202
    refused = auth_client.post(url, json={"input": "two"})

    assert refused.status_code == 429
    assert refused.json()["error"] == "too_many_runs"


# --- waiting for a run's end ---------------------------------------------------------


def test_a_caller_waits_at_most_the_bound_and_the_run_goes_on(database: Database) -> None:
    owner = account(database, "owner")
    executor = BackgroundRunExecutor(max_concurrent=1, grace_seconds=2.0)
    service = RunService(database, executor, 4, RunPolicy(wait_seconds=0.05))
    agent = ScriptedAgent(hold=("role-1",))
    try:
        with pytest.raises(RunStillRunning) as waited:
            service.run_to_end(owner, staged_pipeline(database, owner, [1]), RunStart("x"), agent)

        run = saved_runs(database, owner)[0]
        assert (waited.value.status_code, waited.value.run_id) == (202, run.id)
        assert waited.value.detail == (
            f"Run {run.id} is still going after 0.05 s and continues in the background. "
            f"Follow it with GET /api/runs/{run.id}."
        )
        assert load_run(database, run.id).status in (RunStatus.QUEUED, RunStatus.RUNNING)
    finally:
        agent.release.set()
        executor.shutdown()


def test_the_compatibility_endpoint_answers_202_once_the_wait_is_over(
    app: FastAPI, auth_client: TestClient, session: Session, user: User
) -> None:
    app.dependency_overrides[run_executor] = ParkedExecutor
    app.dependency_overrides[app_settings] = lambda: TEST_SETTINGS.model_copy(
        update={"run_wait_max_seconds": 0.01}
    )
    pipeline: Pipeline = make_pipeline(session, user, "Slow")

    response = auth_client.post(f"/api/pipelines/{pipeline.id}/run", json={"input": "go"})

    assert response.status_code == 202
    body = response.json()
    assert body["error"] == "run_still_running"
    run_id = saved_runs(app.state.database, user)[0].id
    assert f"GET /api/runs/{run_id}" in body["detail"]
    assert auth_client.get(f"/api/runs/{run_id}").json()["status"] == "queued"
