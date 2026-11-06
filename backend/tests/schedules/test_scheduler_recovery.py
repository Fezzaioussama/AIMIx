"""The first tick after a restart starts the occurrence a stopped process claimed but
never started, and a claim never outlives the occurrence it was for."""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.orm import Session

from api.models import Pipeline, RunStatus, RunTrigger, Schedule, User
from api.repositories import schedules as repository
from api.services.schedules.service import run_start
from tests.conftest import FakeProvider
from tests.schedules.support import (
    TOMORROW,
    Clock,
    FlakyAgents,
    StaticAgents,
    at_utc,
    new_schedule,
    run_service,
    runs_of,
    scheduler,
    stored,
    when,
)

#: The schedule's first occurrence, and the one after it.
SLOT = when(25, 9)
NEXT_SLOT = when(26, 9)
#: A minute into the occurrence: the process is back, and the next one is not due.
RESTARTED = when(25, 9, 1)


def claimed_before_a_crash(app: FastAPI, schedule_id: int) -> None:
    """The previous process claimed the 09:00 occurrence (moved the schedule on to
    the next day) and died before its run was saved."""
    with app.state.database.session() as session:
        assert repository.claim(session, schedule_id, SLOT, NEXT_SLOT)
    assert at_utc(stored(app, schedule_id).claimed_occurrence) == SLOT


def test_an_occurrence_claimed_before_a_crash_starts_at_the_first_tick_after(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    schedule = new_schedule(session, user, pipeline.id)  # next: 25 Oct, 09:00 UTC
    claimed_before_a_crash(app, schedule.id)
    agents = StaticAgents(FakeProvider(reply="digest"))

    started = scheduler(app, agents, Clock(RESTARTED)).tick()

    assert started == 1
    (run,) = runs_of(session)
    assert (run.schedule_id, run.trigger) == (schedule.id, RunTrigger.SCHEDULE)
    assert (run.status, run.final_output) == (RunStatus.SUCCEEDED, "digest")
    row = stored(app, schedule.id)
    assert row.claimed_occurrence is None
    assert (row.last_error, at_utc(row.next_run_at)) == ("", NEXT_SLOT)


def test_a_claimed_occurrence_whose_run_was_saved_is_not_started_again(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    schedule = new_schedule(session, user, pipeline.id)
    claimed_before_a_crash(app, schedule.id)
    # Its run was saved after all; the process died just before settling the claim.
    run_service(app).start(user, pipeline, run_start(stored(app, schedule.id)), FakeProvider())
    agents = StaticAgents(FakeProvider(reply="again"))

    started = scheduler(app, agents, Clock(RESTARTED)).tick()

    assert started == 0
    assert [run.final_output for run in runs_of(session)] == ["fake reply"]
    row = stored(app, schedule.id)
    assert (row.claimed_occurrence, row.last_error) == (None, "")


def test_a_schedule_switched_off_since_the_crash_only_settles_its_claim(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    schedule = new_schedule(session, user, pipeline.id)
    claimed_before_a_crash(app, schedule.id)
    with app.state.database.session() as db:
        switched_off = db.get(Schedule, schedule.id)
        assert switched_off is not None
        switched_off.enabled = False
        db.commit()
    agents = StaticAgents(FakeProvider())

    started = scheduler(app, agents, Clock(RESTARTED)).tick()

    assert started == 0
    assert runs_of(session) == []
    assert stored(app, schedule.id).claimed_occurrence is None


def test_a_claim_is_settled_however_the_occurrence_ends(
    app: FastAPI, session: Session, user: User, pipeline: Pipeline
) -> None:
    failing = new_schedule(session, user, pipeline.id)
    fired = new_schedule(session, user, pipeline.id)
    agents = FlakyAgents(FakeProvider(), failures=1)  # the first start has no key

    assert scheduler(app, agents, Clock(TOMORROW)).tick() == 1

    assert stored(app, failing.id).last_error == "No API key is set for openrouter."
    assert stored(app, fired.id).last_error == ""
    assert stored(app, failing.id).claimed_occurrence is None
    assert stored(app, fired.id).claimed_occurrence is None
