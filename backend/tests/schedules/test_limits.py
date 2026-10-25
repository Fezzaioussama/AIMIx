"""What bounds a schedule: the spending limits each of its runs keeps, the
server's ceiling on them, the cap on schedules per account (checked inside the
insert), and one run at a time: an occurrence that comes while the previous
run is still active is skipped."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.db import Database
from api.deps import app_settings
from api.exceptions import ValidationFailed
from api.models import Base, Pipeline, RunStatus, User
from api.repositories import active_runs, users
from api.repositories import schedules as repository
from api.services.run_budget import RunBudget
from api.services.run_policy import RunPolicy
from api.services.runs import RunService, RunStart
from api.services.schedules.scheduler import Scheduler
from api.services.schedules.service import ScheduleAccess, ScheduleDraft, create
from tests.conftest import TEST_SETTINGS, FakeProvider
from tests.schedules.support import (
    DAILY_AT_NINE,
    NOW,
    TOMORROW,
    Clock,
    StaticAgents,
    at_utc,
    body,
    create_schedule,
    new_schedule,
    runs_of,
    scheduler,
    stored,
    when,
)
from tests.test_endpoints import make_pipeline
from tests.test_runs_service import ParkedExecutor

LIMITS = {"max_cost_usd": 0.75, "max_tokens": 4000}


def test_a_schedule_keeps_its_runs_limits_and_its_runs_start_with_them(
    api: TestClient, pipeline: Pipeline
) -> None:
    created = create_schedule(api, pipeline, **LIMITS)

    assert (created["max_cost_usd"], created["max_tokens"]) == (0.75, 4000)
    run = api.post(f"/api/schedules/{created['id']}/run").json()
    assert (run["max_cost_usd"], run["max_tokens"]) == (0.75, 4000)


def test_the_scheduler_starts_each_run_with_the_schedules_limits(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    draft = ScheduleDraft(pipeline.id, DAILY_AT_NINE, RunStart("go", budget=RunBudget(0.75, 4000)))
    create(ScheduleAccess(session, user, 20, NOW), draft)

    scheduler(app, StaticAgents(FakeProvider()), Clock(TOMORROW)).tick()

    (run,) = runs_of(session)
    assert (run.max_cost_usd, run.max_tokens) == (0.75, 4000)


def test_editing_the_limits_replaces_both_and_null_removes_one(
    api: TestClient, pipeline: Pipeline
) -> None:
    schedule = create_schedule(api, pipeline, **LIMITS)
    url = f"/api/schedules/{schedule['id']}"

    kept = api.patch(url, json={"time": "10:00"}).json()
    assert (kept["max_cost_usd"], kept["max_tokens"]) == (0.75, 4000)
    changed = api.patch(url, json={"max_cost_usd": 2.0}).json()
    assert (changed["max_cost_usd"], changed["max_tokens"]) == (2.0, None)
    cleared = api.patch(url, json={"max_cost_usd": None}).json()
    assert (cleared["max_cost_usd"], cleared["max_tokens"]) == (None, None)


def test_a_schedule_cannot_ask_for_more_than_the_ceiling(
    app: FastAPI, api: TestClient, pipeline: Pipeline
) -> None:
    capped = TEST_SETTINGS.model_copy(update={"run_max_cost_usd": 0.5})
    app.dependency_overrides[app_settings] = lambda: capped

    refused = api.post("/api/schedules", json=body(pipeline, max_cost_usd=0.75))
    assert (refused.status_code, refused.json()["error"]) == (400, "validation_error")
    assert "at most a $0.50 limit" in refused.json()["detail"]

    schedule = create_schedule(api, pipeline, max_cost_usd=0.5)
    patched = api.patch(f"/api/schedules/{schedule['id']}", json={"max_cost_usd": 3.0})
    assert patched.status_code == 400
    assert stored(app, schedule["id"]).max_cost_usd == 0.5


# --- one run at a time ---------------------------------------------------------------


def test_an_occurrence_is_skipped_while_the_previous_run_is_still_active(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    schedule = new_schedule(session, user, pipeline.id)  # daily at 09:00 UTC
    parked = RunService(app.state.database, ParkedExecutor(), 2)
    clock = Clock(TOMORROW)
    ticking = Scheduler(app.state.database, parked, StaticAgents(FakeProvider()), clock)
    assert ticking.tick() == 1  # its run stays queued, as one that takes long would

    clock.advance(days=1)
    assert ticking.tick() == 0

    (only,) = runs_of(session)
    assert only.status == RunStatus.QUEUED
    row = stored(app, schedule.id)
    assert row.last_error == f"Skipped a run: run {only.id} of this schedule was still in progress."
    # The skipped time (the 26th) is gone: the schedule waits for its next one.
    assert at_utc(row.next_run_at) == when(27, 9)


def test_once_the_previous_run_ends_the_next_time_starts_again(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    schedule = new_schedule(session, user, pipeline.id)
    clock = Clock(TOMORROW)
    agents = StaticAgents(FakeProvider())
    scheduler(app, agents, clock).tick()  # inline: the run ends inside the tick
    with app.state.database.session() as fresh:
        assert active_runs.of_schedule(fresh, schedule.id) is None

    clock.advance(days=1)
    assert scheduler(app, agents, clock).tick() == 1
    assert len(runs_of(session)) == 2
    assert stored(app, schedule.id).last_error == ""


def test_a_scheduled_run_over_the_accounts_cap_says_so_on_the_schedule(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    first = new_schedule(session, user, pipeline.id)
    second = new_schedule(session, user, make_pipeline(session, user, "Other").id)
    capped = RunService(app.state.database, ParkedExecutor(), 2, RunPolicy(max_active_per_user=1))
    clock = Clock(TOMORROW)

    started = Scheduler(app.state.database, capped, StaticAgents(FakeProvider()), clock).tick()

    assert started == 1
    assert len(runs_of(session)) == 1
    errors = {stored(app, first.id).last_error, stored(app, second.id).last_error}
    assert "" in errors
    assert any("You already have 1 run queued, running or waiting" in e for e in errors)


# --- the cap on schedules --------------------------------------------------------------


@pytest.fixture
def file_database(tmp_path: Path) -> Iterator[Database]:
    db = Database(f"sqlite:///{tmp_path / 'schedules.sqlite3'}")
    Base.metadata.create_all(db.engine)
    yield db
    db.engine.dispose()


def test_creates_at_the_same_moment_cannot_pass_the_cap_together(file_database: Database) -> None:
    with file_database.session() as session:
        owner = users.create(session, "owner", "hash")
        pipeline_id = make_pipeline(session, owner, "Digest").id
    gate = threading.Barrier(5)
    outcomes: list[str] = []

    draft = ScheduleDraft(pipeline_id, DAILY_AT_NINE, RunStart("go"))

    def add() -> None:
        with file_database.session() as session:
            gate.wait()
            try:
                create(ScheduleAccess(session, owner, 2, NOW), draft)
                outcomes.append("created")
            except ValidationFailed:
                outcomes.append("refused")

    threads = [threading.Thread(target=add) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["created"] * 2 + ["refused"] * 3
    with file_database.session() as session:
        assert repository.count(session, owner) == 2


def test_the_cap_is_checked_in_the_insert_itself(session: Session, user: User) -> None:
    pipeline_id = make_pipeline(session, user, "Digest").id
    draft = ScheduleDraft(pipeline_id, DAILY_AT_NINE, RunStart("go"))
    create(ScheduleAccess(session, user, 1, NOW), draft)

    with pytest.raises(ValidationFailed, match="up to 1 schedules"):
        create(ScheduleAccess(session, user, 1, NOW), draft)

    # Nothing of the refused insert is kept, and the session stays usable.
    assert repository.count(session, user) == 1
    create(ScheduleAccess(session, user, 2, NOW), draft)
    assert repository.count(session, user) == 2
