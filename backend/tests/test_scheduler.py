"""The scheduler: each due occurrence starts exactly one run of its own, the
same way a manual run starts, and a failure to start is recorded on the
schedule. Ticks are driven by a test clock and the inline executor."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import time, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.db import Database
from api.models import Base, Pipeline, Run, RunStatus, RunTrigger, User
from api.repositories import pipelines, users
from api.repositories import schedules as repository
from api.repositories.pipelines import PipelineChanges
from api.security import SecretBox, hash_password
from api.services import llm_settings
from api.services.catalog import default_model_id
from api.services.llm_settings import ProviderChoice, SettingsUpdate
from api.services.multiagent.step_agent import PipelineAgentGenerator
from api.services.run_recorder import SERVER_ERROR_DETAIL
from api.services.runs import RunService, RunStart
from api.services.schedules.scheduler import (
    IdleScheduler,
    ProfileAgents,
    Scheduler,
    SchedulerLoop,
    build_scheduler,
)
from api.services.schedules.service import ScheduleEdit, TimingEdit, update
from tests.conftest import TEST_SETTINGS, FakeProvider, InlineRunExecutor
from tests.schedule_support import (
    HOURLY_AT_QUARTER_PAST,
    NOW,
    BrokenAgents,
    Clock,
    FlakyAgents,
    StaticAgents,
    access,
    at_utc,
    new_schedule,
    run_service,
    scheduler,
    stored,
)
from tests.test_agent_tools import one_step
from tests.test_endpoints import make_pipeline

WAIT_SECONDS = 5.0
TOMORROW = NOW + timedelta(days=1)  # 12:00 on the 25th, after that day's 09:00 time


def runs_of(session: Session) -> list[Run]:
    session.expire_all()
    return list(session.query(Run).order_by(Run.id))


@pytest.fixture
def pipeline(session: Session, user: User) -> Pipeline:
    return make_pipeline(session, user, "Weekly digest")


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
    new_schedule(session, user, named.id, start=RunStart("", {"topic": "bees"}))
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


# --- two processes ----------------------------------------------------------------


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


# --- failures ---------------------------------------------------------------------


def test_a_run_that_cannot_start_is_recorded_and_the_schedule_moves_on(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    schedule = new_schedule(session, user, pipeline.id)
    clock = Clock(TOMORROW)
    tick = scheduler(app, FlakyAgents(FakeProvider(), failures=1), clock)

    assert tick.tick() == 0

    row = stored(app, schedule.id)
    assert row.last_error == "No API key is set for openrouter."
    assert at_utc(row.next_run_at) == NOW.replace(day=26, hour=9, minute=0)
    assert runs_of(session) == []
    # Its next time starts normally, and the error is cleared.
    clock.advance(days=1)
    assert tick.tick() == 1
    assert stored(app, schedule.id).last_error == ""
    assert len(runs_of(session)) == 1


def test_an_account_without_an_api_key_cannot_start_a_scheduled_run(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    schedule = new_schedule(session, user, pipeline.id)
    clock = Clock(TOMORROW)
    agents = ProfileAgents(app.state.database, SecretBox(TEST_SETTINGS.secret_key))

    assert Scheduler(app.state.database, run_service(app), agents, clock).tick() == 0

    assert "No API key is set for openrouter" in stored(app, schedule.id).last_error
    assert runs_of(session) == []


def test_a_saved_key_gives_the_owner_a_step_agent_of_their_own(
    app: FastAPI, session: Session, user: User
) -> None:
    box = SecretBox(TEST_SETTINGS.secret_key)
    choice = ProviderChoice("openrouter", default_model_id("openrouter"), "sk-or-test-1234")
    llm_settings.save(session, user, box, SettingsUpdate("openrouter", [choice]))

    agent = ProfileAgents(app.state.database, box)(session, user)

    assert isinstance(agent, PipelineAgentGenerator)


def test_inputs_the_pipeline_no_longer_takes_are_recorded_on_the_schedule(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    schedule = new_schedule(session, user, pipeline.id)  # saved with free text
    topic = {"name": "topic", "label": "", "description": ""}
    pipelines.replace_steps(session, pipeline, PipelineChanges(inputs=[topic]))
    provider = FakeProvider()

    scheduler(app, StaticAgents(provider), Clock(TOMORROW)).tick()

    assert "named inputs instead of text" in stored(app, schedule.id).last_error
    assert provider.calls == []
    assert runs_of(session) == []


def test_a_pipeline_that_lost_its_steps_is_recorded_on_the_schedule(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    schedule = new_schedule(session, user, pipeline.id)
    pipelines.replace_steps(session, pipeline, PipelineChanges(steps=[]))

    scheduler(app, StaticAgents(FakeProvider()), Clock(TOMORROW)).tick()

    assert stored(app, schedule.id).last_error == "This pipeline has no steps to run."


def test_a_bug_in_one_schedule_does_not_stop_the_others(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    stranger = users.create(session, "stranger", hash_password("x-pass-2891", 1))
    theirs = make_pipeline(session, stranger, "Theirs")
    broken = new_schedule(session, user, pipeline.id)
    fine = new_schedule(session, stranger, theirs.id)
    agents = BrokenAgents(FakeProvider(), broken={user.id})

    started = scheduler(app, agents, Clock(TOMORROW)).tick()

    assert started == 1
    assert stored(app, broken.id).last_error == SERVER_ERROR_DETAIL
    assert stored(app, fine.id).last_error == ""
    assert [run.schedule_id for run in runs_of(session)] == [fine.id]


def test_recording_an_error_for_a_schedule_that_is_gone_changes_nothing(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    schedule = new_schedule(session, user, pipeline.id)
    with app.state.database.session() as db:
        repository.delete(db, repository.get_owned(db, user, schedule.id))

    with app.state.database.session() as db:
        repository.set_last_error(db, schedule.id, "ignored")
        assert repository.get(db, schedule.id) is None


# --- the loop and the app ---------------------------------------------------------


def test_the_loop_ticks_until_it_is_stopped() -> None:
    enough = threading.Event()
    calls: list[int] = []

    def tick() -> None:
        calls.append(1)
        if len(calls) == 3:
            enough.set()

    loop = SchedulerLoop(tick, interval=0.001, grace=WAIT_SECONDS)
    loop.start()
    loop.start()  # a second start changes nothing
    assert enough.wait(WAIT_SECONDS)
    loop.stop()
    count = len(calls)
    loop.stop()  # and neither does a second stop

    assert len(calls) == count  # nothing ticks once stop has returned


def test_a_failing_tick_does_not_end_the_loop() -> None:
    survived = threading.Event()
    calls: list[int] = []

    def tick() -> None:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("the database is briefly unavailable")
        survived.set()

    loop = SchedulerLoop(tick, interval=0.001, grace=WAIT_SECONDS)
    loop.start()
    try:
        assert survived.wait(WAIT_SECONDS)
    finally:
        loop.stop()


def test_a_stopped_loop_can_start_again() -> None:
    ticked = threading.Event()
    loop = SchedulerLoop(ticked.set, interval=0.001, grace=WAIT_SECONDS)

    loop.start()
    assert ticked.wait(WAIT_SECONDS)
    loop.stop()
    ticked.clear()
    loop.start()
    try:
        assert ticked.wait(WAIT_SECONDS)
    finally:
        loop.stop()


def test_the_scheduler_is_built_from_settings(app: FastAPI) -> None:
    database, executor = app.state.database, app.state.run_executor
    enabled = TEST_SETTINGS.model_copy(update={"scheduler_enabled": True})

    idle = build_scheduler(database, executor, TEST_SETTINGS)
    idle.start()
    idle.stop()

    assert isinstance(idle, IdleScheduler)
    assert isinstance(build_scheduler(database, executor, enabled), SchedulerLoop)


class Recorder:
    """Stands in for the scheduler and the executor, noting when each starts or stops."""

    def __init__(self, events: list[str]) -> None:
        self.events = events

    def start(self) -> None:
        self.events.append("scheduler started")

    def stop(self) -> None:
        self.events.append("scheduler stopped")

    def shutdown(self) -> None:
        self.events.append("executor stopped")


def test_the_app_starts_the_scheduler_and_stops_it_before_the_executor(app: FastAPI) -> None:
    events: list[str] = []
    recorder = Recorder(events)
    app.state.scheduler = recorder
    app.state.run_executor = recorder

    with TestClient(app):
        assert events == ["scheduler started"]

    assert events == ["scheduler started", "scheduler stopped", "executor stopped"]
