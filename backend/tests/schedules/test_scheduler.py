"""The scheduler: each due occurrence starts exactly one run of its own, the same way a
manual run starts. Ticks are driven by a test clock and the inline executor."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import time, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from api.db import Database
from api.models import Base, Pipeline, Run, RunStatus, RunTrigger, User
from api.repositories import pipelines, users
from api.repositories import schedules as repository
from api.security import hash_password
from api.services.runs import RunService, RunStart
from api.services.schedules.scheduler import Scheduler
from api.services.schedules.service import ScheduleDraft, ScheduleEdit, TimingEdit, create, update
from tests.conftest import FakeProvider, InlineRunExecutor
from tests.schedules.support import (
    DAILY_AT_NINE,
    HOURLY_AT_QUARTER_PAST,
    NOW,
    TOMORROW,
    WAIT_SECONDS,
    Clock,
    StaticAgents,
    access,
    at_utc,
    new_schedule,
    runs_of,
    scheduler,
    stored,
)
from tests.test_agent_tools import one_step
from tests.test_endpoints import make_pipeline


def test_a_due_schedule_starts_a_run_marked_as_its_own(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    schedule = new_schedule(session, user, pipeline.id)  # next: 25 Oct, 09:00 UTC
    agents = StaticAgents(FakeProvider(reply="digest"))
    clock = Clock(NOW + timedelta(hours=21, seconds=5))  # 09:00:05 on the 25th

    started = scheduler(app, agents, clock).tick()

    assert started == 1
    (run,) = runs_of(session)
    assert (run.trigger, run.schedule_id) == (RunTrigger.SCHEDULE, schedule.id)
    assert (run.user_id, run.pipeline_id, run.input_text) == (user.id, pipeline.id, "go")
    assert (run.status, run.final_output) == (RunStatus.SUCCEEDED, "digest")
    assert agents.owners == [user.id]
    row = stored(app, schedule.id)
    assert at_utc(row.next_run_at) == NOW.replace(day=26, hour=9, minute=0)
    assert row.last_error == ""


def test_the_run_takes_the_named_values_the_schedule_was_saved_with(
    app: FastAPI, session: Session, user: User
) -> None:
    topic = {"name": "topic", "label": "Topic", "description": ""}
    named = pipelines.create_with_steps(
        session, user, one_step("Post", "Write about {topic}", inputs=[topic])
    )
    draft = ScheduleDraft(named.id, DAILY_AT_NINE, RunStart("", {"topic": "bees"}))
    create(access(session, user), draft)
    provider = FakeProvider(reply="post")

    scheduler(app, StaticAgents(provider), Clock(TOMORROW)).tick()

    assert provider.calls == [("Write about bees", "m")]
    assert runs_of(session)[0].input_values == {"topic": "bees"}


def test_nothing_runs_before_its_time_or_while_the_schedule_is_off(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    waiting = new_schedule(session, user, pipeline.id)
    off = new_schedule(session, user, pipeline.id)
    update(access(session, user), off.id, ScheduleEdit(enabled=False))
    agents = StaticAgents(FakeProvider())
    clock = Clock(NOW + timedelta(hours=20, minutes=59, seconds=59))  # 08:59:59 on the 25th

    assert scheduler(app, agents, clock).tick() == 0
    assert runs_of(session) == []

    # Days later the waiting schedule starts; the one that is off never does.
    clock.advance(days=3)
    assert scheduler(app, agents, clock).tick() == 1
    assert [run.schedule_id for run in runs_of(session)] == [waiting.id]
    assert stored(app, off.id).next_run_at is None


def test_a_schedule_overdue_after_downtime_runs_once_not_once_per_missed_time(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    schedule = new_schedule(session, user, pipeline.id, HOURLY_AT_QUARTER_PAST)
    clock = Clock(NOW + timedelta(days=5, minutes=7))  # a hundred and twenty missed times
    tick = scheduler(app, StaticAgents(FakeProvider()), clock)

    assert tick.tick() == 1
    assert tick.tick() == 0  # the same instant again: nothing more is due

    assert len(runs_of(session)) == 1
    next_run = at_utc(stored(app, schedule.id).next_run_at)
    assert clock.now < next_run <= clock.now + timedelta(hours=1)
    clock.advance(hours=1)
    assert tick.tick() == 1
    assert len(runs_of(session)) == 2


def test_every_due_schedule_starts_with_its_own_owners_agent(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    stranger = users.create(session, "stranger", hash_password("x-pass-2891", 1))
    theirs = make_pipeline(session, stranger, "Theirs")
    mine = new_schedule(session, user, pipeline.id)
    other = new_schedule(session, stranger, theirs.id)
    agents = StaticAgents(FakeProvider())

    scheduler(app, agents, Clock(TOMORROW)).tick()

    assert sorted(agents.owners) == sorted([user.id, stranger.id])
    owners = {run.schedule_id: run.user_id for run in runs_of(session)}
    assert owners == {mine.id: user.id, other.id: stranger.id}


def test_a_process_that_listed_the_occurrence_too_late_starts_nothing(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    schedule = new_schedule(session, user, pipeline.id)
    clock = Clock(TOMORROW)
    first = scheduler(app, StaticAgents(FakeProvider()), clock)
    second = scheduler(app, StaticAgents(FakeProvider()), clock)
    # Both processes listed the schedule as due before either claimed it.
    with app.state.database.session() as listing:
        (snapshot,) = repository.due(listing, clock.now)
    assert snapshot.id == schedule.id

    results = [first.fire(snapshot, clock.now), second.fire(snapshot, clock.now)]

    assert results == [True, False]
    assert len(runs_of(session)) == 1


@pytest.fixture
def file_database(tmp_path: Path) -> Iterator[Database]:
    """One connection per thread, as in production (the in-memory test database
    shares a single connection)."""
    database = Database(f"sqlite:///{tmp_path / 'schedules.sqlite3'}")
    Base.metadata.create_all(database.engine)
    yield database
    database.engine.dispose()


def test_processes_racing_for_one_occurrence_start_exactly_one_run(
    file_database: Database,
) -> None:
    with file_database.session() as session:
        owner = users.create(session, "racer", "hash")
        saved = pipelines.create_with_steps(session, owner, one_step("Race", "{input}"))
        new_schedule(session, owner, saved.id)
    clock = Clock(TOMORROW)
    with file_database.session() as listing:
        (snapshot,) = repository.due(listing, clock.now)
    racers = 6
    barrier = threading.Barrier(racers)
    results: list[bool] = []

    def race() -> None:
        runs = RunService(file_database, InlineRunExecutor(), max_parallel_steps=2)
        tick = Scheduler(file_database, runs, StaticAgents(FakeProvider()), clock)
        barrier.wait(WAIT_SECONDS)  # all of them claim at the same moment
        results.append(tick.fire(snapshot, clock.now))

    threads = [threading.Thread(target=race) for _ in range(racers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(WAIT_SECONDS)

    assert sorted(results) == [False] * (racers - 1) + [True]
    with file_database.session() as session:
        assert session.query(Run).count() == 1


def test_claiming_applies_only_to_the_occurrence_that_was_seen(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    schedule = new_schedule(session, user, pipeline.id)
    seen = stored(app, schedule.id).next_run_at
    assert seen is not None
    later = seen + timedelta(days=1)

    with app.state.database.session() as db:
        assert repository.claim(db, schedule.id, seen + timedelta(minutes=1), later) is False
        assert repository.claim(db, schedule.id, seen, later) is True
        assert repository.claim(db, schedule.id, seen, later + timedelta(days=1)) is False
    assert stored(app, schedule.id).next_run_at == later


def test_a_schedule_edited_after_it_was_listed_is_not_started_for_the_old_time(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    schedule = new_schedule(session, user, pipeline.id)
    clock = Clock(TOMORROW)
    with app.state.database.session() as listing:
        (snapshot,) = repository.due(listing, clock.now)
    # Its owner moves it to the evening, so its next time is no longer the one listed.
    update(access(session, user, clock.now), schedule.id, ScheduleEdit(TimingEdit(at=time(20, 0))))

    assert scheduler(app, StaticAgents(FakeProvider()), clock).fire(snapshot, clock.now) is False

    assert runs_of(session) == []


def test_a_run_uses_the_inputs_saved_when_it_starts(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    schedule = new_schedule(session, user, pipeline.id)
    clock = Clock(TOMORROW)
    with app.state.database.session() as listing:
        (snapshot,) = repository.due(listing, clock.now)
    # The inputs change after the tick listed it; its due time does not.
    update(access(session, user, clock.now), schedule.id, ScheduleEdit(start=RunStart("edited")))

    assert scheduler(app, StaticAgents(FakeProvider()), clock).fire(snapshot, clock.now) is True

    assert runs_of(session)[0].input_text == "edited"
