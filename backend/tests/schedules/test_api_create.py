"""Creating and listing schedules over HTTP: the next run, what each frequency keeps, every
refusal, ownership and the per-account limit. Time is the test clock's; runs execute inline."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.models import Pipeline, User
from api.repositories import pipelines
from tests.conftest import bearer
from tests.schedules.support import NOW, PARIS, Clock, body, create_schedule, listing, parse, when
from tests.test_agent_tools import one_step
from tests.test_endpoints import make_pipeline

SCHEDULE_KEYS = {
    "id",
    "pipeline_id",
    "pipeline_name",
    "pipeline_inputs",
    "frequency",
    "time",
    "weekday",
    "day_of_month",
    "timezone",
    "input",
    "inputs",
    "enabled",
    "next_run_at",
    "last_run",
    "last_error",
    "created_at",
}


def test_a_schedule_is_created_with_its_next_run(api: TestClient, pipeline: Pipeline) -> None:
    created = create_schedule(api, pipeline)

    assert set(created) == SCHEDULE_KEYS
    assert (created["pipeline_id"], created["pipeline_name"]) == (pipeline.id, "Digest")
    assert (created["frequency"], created["time"], created["timezone"]) == ("daily", "09:00", PARIS)
    assert (created["weekday"], created["day_of_month"]) == (None, None)
    assert (created["input"], created["inputs"], created["enabled"]) == ("go", {}, True)
    assert created["pipeline_inputs"] == []
    # 09:00 in Paris on the 25th, after the clocks have gone back: 08:00 UTC.
    assert parse(created["next_run_at"]) == when(25, 8)
    assert (created["last_run"], created["last_error"]) == (None, None)
    assert parse(created["created_at"]).tzinfo is not None
    assert listing(api) == [created]


def test_each_frequency_keeps_only_the_fields_it_uses(api: TestClient, pipeline: Pipeline) -> None:
    hourly = create_schedule(
        api, pipeline, frequency="hourly", time="07:30", weekday=2, day_of_month=9
    )
    weekly = create_schedule(api, pipeline, frequency="weekly", weekday=0, day_of_month=9)
    monthly = create_schedule(api, pipeline, frequency="monthly", day_of_month=31, weekday=2)

    assert (hourly["time"], hourly["weekday"], hourly["day_of_month"]) == ("00:30", None, None)
    assert parse(hourly["next_run_at"]) == when(24, 12, 30)
    assert (weekly["weekday"], weekly["day_of_month"]) == (0, None)
    assert parse(weekly["next_run_at"]) == when(26, 8)  # Monday, 09:00 in Paris
    assert (monthly["weekday"], monthly["day_of_month"]) == (None, 31)
    assert parse(monthly["next_run_at"]) == when(31, 8)


def test_a_schedule_can_be_created_off(api: TestClient, pipeline: Pipeline) -> None:
    created = create_schedule(api, pipeline, enabled=False)

    assert (created["enabled"], created["next_run_at"]) == (False, None)


@pytest.mark.parametrize(
    ("fields", "problem"),
    [
        ({"timezone": "Mars/Olympus"}, "Unknown time zone 'Mars/Olympus'"),
        ({"timezone": ""}, "timezone"),
        ({"time": "9:00"}, "time"),
        ({"time": "24:00"}, "time"),
        ({"time": "09:60"}, "time"),
        ({"frequency": "yearly"}, "frequency"),
        ({"frequency": "weekly"}, "day of the week"),
        ({"frequency": "weekly", "weekday": 7}, "weekday"),
        ({"frequency": "monthly"}, "day of the month"),
        ({"frequency": "monthly", "day_of_month": 32}, "day_of_month"),
        ({"frequency": "monthly", "day_of_month": 0}, "day_of_month"),
        ({"input": "   "}, "must not be blank"),
        ({"inputs": {"topic": "bees"}}, "no named inputs"),
    ],
)
def test_a_schedule_that_could_not_run_is_refused_and_nothing_is_saved(
    api: TestClient, pipeline: Pipeline, fields: dict[str, Any], problem: str
) -> None:
    response = api.post("/api/schedules", json=body(pipeline, **fields))

    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"
    assert problem in response.json()["detail"]
    assert listing(api) == []


def test_a_pipeline_needs_every_one_of_its_named_inputs(
    api: TestClient, session: Session, user: User
) -> None:
    topic = {"name": "topic", "label": "Topic", "description": ""}
    tone = {"name": "tone", "label": "", "description": ""}
    named = pipelines.create_with_steps(
        session, user, one_step("Post", "{topic} {tone}", inputs=[topic, tone])
    )

    def attempt(**fields: Any) -> Any:
        return api.post("/api/schedules", json=body(named, **{"input": "", **fields}))

    assert "Fill in Topic" in attempt(inputs={"tone": "calm"}).json()["detail"]
    assert (
        "Unknown input 'mood'"
        in attempt(inputs={"topic": "a", "tone": "b", "mood": "c"}).json()["detail"]
    )
    assert "named inputs instead of text" in attempt(input="free text").json()["detail"]
    created = attempt(inputs={"topic": "bees", "tone": "calm"})
    assert created.status_code == 201
    assert created.json()["inputs"] == {"topic": "bees", "tone": "calm"}
    assert created.json()["pipeline_inputs"] == [topic, tone]


def test_a_pipeline_without_steps_cannot_be_scheduled(
    api: TestClient, session: Session, user: User
) -> None:
    empty = pipelines.create_with_steps(session, user, pipelines.PipelineChanges("Empty", steps=[]))

    response = api.post("/api/schedules", json=body(empty))

    assert response.status_code == 400
    assert "no steps" in response.json()["detail"]


def test_someone_elses_or_a_missing_pipeline_is_a_404(
    api: TestClient, session: Session, stranger: User
) -> None:
    theirs = make_pipeline(session, stranger, "Theirs")

    for pipeline_id in (theirs.id, 9999):
        response = api.post("/api/schedules", json={**body(theirs), "pipeline_id": pipeline_id})
        assert (response.status_code, response.json()["error"]) == (404, "not_found")
    assert listing(api) == []


def test_each_account_may_have_a_limited_number_of_schedules(
    api: TestClient, pipeline: Pipeline, session: Session, stranger: User
) -> None:
    for _ in range(3):  # SCHEDULES_MAX_PER_USER in the test settings
        create_schedule(api, pipeline)

    refused = api.post("/api/schedules", json=body(pipeline))

    assert refused.status_code == 400
    assert "up to 3 schedules" in refused.json()["detail"]
    theirs = make_pipeline(session, stranger, "Theirs")
    ok = api.post("/api/schedules", json=body(theirs), headers=bearer(stranger))
    assert ok.status_code == 201
    # Deleting one makes room.
    api.delete(f"/api/schedules/{listing(api)[0]['id']}")
    assert api.post("/api/schedules", json=body(pipeline)).status_code == 201


def test_the_list_holds_only_your_schedules_oldest_first_and_can_be_filtered(
    api: TestClient, session: Session, pipeline: Pipeline, stranger: User
) -> None:
    other = make_pipeline(session, stranger, "Theirs")
    second_pipeline = make_pipeline(session, pipeline.user, "Second")
    first = create_schedule(api, pipeline, time="08:00")
    second = create_schedule(api, second_pipeline, time="10:00")
    third = create_schedule(api, pipeline, time="11:00")
    api.post("/api/schedules", json=body(other), headers=bearer(stranger))

    assert [item["id"] for item in listing(api)] == [first["id"], second["id"], third["id"]]
    only = listing(api, pipeline_id=pipeline.id)
    assert [item["id"] for item in only] == [first["id"], third["id"]]
    assert listing(api, pipeline_id=other.id) == []  # not theirs to see


def test_the_time_a_schedule_is_created_at_is_the_requests_now(
    api: TestClient, pipeline: Pipeline, clock: Clock
) -> None:
    clock.now = NOW + timedelta(days=10)  # Tuesday 3 Nov

    created = create_schedule(api, pipeline)

    assert parse(created["next_run_at"]) == when(4, 8, month=11)
