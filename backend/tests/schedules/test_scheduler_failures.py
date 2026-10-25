"""When a scheduled run cannot start: the reason is recorded on the schedule, logged, and the
schedule moves on to its next time without stopping the others."""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.orm import Session

from api.models import Pipeline, User
from api.repositories import pipelines, users
from api.repositories import schedules as repository
from api.repositories.pipelines import PipelineChanges
from api.security import SecretBox, hash_password
from api.services import llm_settings
from api.services.catalog import default_model_id
from api.services.llm_settings import ProviderChoice, SettingsUpdate
from api.services.multiagent.step_agent import PipelineAgentGenerator
from api.services.run_recorder import SERVER_ERROR_DETAIL
from api.services.schedules.scheduler import ProfileAgents, Scheduler
from tests.conftest import TEST_SETTINGS, FakeProvider
from tests.schedules.support import (
    NOW,
    TOMORROW,
    BrokenAgents,
    Clock,
    FlakyAgents,
    StaticAgents,
    at_utc,
    new_schedule,
    run_service,
    runs_of,
    scheduler,
    stored,
)
from tests.test_endpoints import make_pipeline


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
