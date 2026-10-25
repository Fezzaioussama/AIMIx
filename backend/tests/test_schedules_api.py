"""HTTP surface of schedules: create, list, change, delete, run now and preview,
scoped to their owner. Time is the test clock's; runs execute inline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.deps import current_time
from api.models import Pipeline, User
from api.repositories import pipelines, users
from api.repositories import schedules as repository
from api.security import hash_password
from llm import exceptions as llm_exceptions
from tests.conftest import FailingProvider, FakeProvider, bearer, use_pipeline_generator
from tests.schedule_support import NOW, Clock
from tests.test_agent_tools import one_step
from tests.test_endpoints import make_pipeline

PARIS = "Europe/Paris"
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


def parse(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def utc(day: int, hour: int, minute: int = 0, month: int = 10) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=timezone.utc)


def body(pipeline: Pipeline, **fields: Any) -> dict[str, Any]:
    return {
        "pipeline_id": pipeline.id,
        "frequency": "daily",
        "time": "09:00",
        "timezone": PARIS,
        "input": "go",
        **fields,
    }


def create(client: TestClient, pipeline: Pipeline, **fields: Any) -> dict[str, Any]:
    response = client.post("/api/schedules", json=body(pipeline, **fields))
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def listing(client: TestClient, **params: Any) -> list[dict[str, Any]]:
    response = client.get("/api/schedules", params=params)
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()
    return items


@pytest.fixture
def clock(app: FastAPI) -> Clock:
    clock = Clock()
    app.dependency_overrides[current_time] = clock
    return clock


@pytest.fixture
def pipeline(session: Session, user: User) -> Pipeline:
    return make_pipeline(session, user, "Digest")


@pytest.fixture
def stranger(session: Session) -> User:
    return users.create(session, "stranger", hash_password("x-pass-2891", 1))


@pytest.fixture
def api(auth_client: TestClient, clock: Clock, fake_provider: FakeProvider) -> TestClient:
    """A signed-in client on the test clock, whose pipeline agents are fake."""
    return auth_client


# --- create -----------------------------------------------------------------------


def test_a_schedule_is_created_with_its_next_run(api: TestClient, pipeline: Pipeline) -> None:
    created = create(api, pipeline)

    assert set(created) == SCHEDULE_KEYS
    assert (created["pipeline_id"], created["pipeline_name"]) == (pipeline.id, "Digest")
    assert (created["frequency"], created["time"], created["timezone"]) == ("daily", "09:00", PARIS)
    assert (created["weekday"], created["day_of_month"]) == (None, None)
    assert (created["input"], created["inputs"], created["enabled"]) == ("go", {}, True)
    assert created["pipeline_inputs"] == []
    # 09:00 in Paris on the 25th, after the clocks have gone back: 08:00 UTC.
    assert parse(created["next_run_at"]) == utc(25, 8)
    assert (created["last_run"], created["last_error"]) == (None, None)
    assert parse(created["created_at"]).tzinfo is not None
    assert listing(api) == [created]


def test_each_frequency_keeps_only_the_fields_it_uses(api: TestClient, pipeline: Pipeline) -> None:
    hourly = create(api, pipeline, frequency="hourly", time="07:30", weekday=2, day_of_month=9)
    weekly = create(api, pipeline, frequency="weekly", weekday=0, day_of_month=9)
    monthly = create(api, pipeline, frequency="monthly", day_of_month=31, weekday=2)

    assert (hourly["time"], hourly["weekday"], hourly["day_of_month"]) == ("00:30", None, None)
    assert parse(hourly["next_run_at"]) == utc(24, 12, 30)
    assert (weekly["weekday"], weekly["day_of_month"]) == (0, None)
    assert parse(weekly["next_run_at"]) == utc(26, 8)  # Monday, 09:00 in Paris
    assert (monthly["weekday"], monthly["day_of_month"]) == (None, 31)
    assert parse(monthly["next_run_at"]) == utc(31, 8)


def test_a_schedule_can_be_created_off(api: TestClient, pipeline: Pipeline) -> None:
    created = create(api, pipeline, enabled=False)

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
        create(api, pipeline)

    refused = api.post("/api/schedules", json=body(pipeline))

    assert refused.status_code == 400
    assert "up to 3 schedules" in refused.json()["detail"]
    theirs = make_pipeline(session, stranger, "Theirs")
    ok = api.post("/api/schedules", json=body(theirs), headers=bearer(stranger))
    assert ok.status_code == 201
    # Deleting one makes room.
    api.delete(f"/api/schedules/{listing(api)[0]['id']}")
    assert api.post("/api/schedules", json=body(pipeline)).status_code == 201


# --- list -------------------------------------------------------------------------


def test_the_list_holds_only_your_schedules_oldest_first_and_can_be_filtered(
    api: TestClient, session: Session, user: User, pipeline: Pipeline, stranger: User
) -> None:
    other = make_pipeline(session, stranger, "Theirs")
    second_pipeline = make_pipeline(session, user, "Second")
    first = create(api, pipeline, time="08:00")
    second = create(api, second_pipeline, time="10:00")
    third = create(api, pipeline, time="11:00")
    api.post("/api/schedules", json=body(other), headers=bearer(stranger))

    assert [item["id"] for item in listing(api)] == [first["id"], second["id"], third["id"]]
    only = listing(api, pipeline_id=pipeline.id)
    assert [item["id"] for item in only] == [first["id"], third["id"]]
    assert listing(api, pipeline_id=other.id) == []  # not theirs to see


# --- change -----------------------------------------------------------------------


def test_changing_the_time_works_out_the_next_run_again(
    api: TestClient, pipeline: Pipeline
) -> None:
    schedule = create(api, pipeline)

    evening = api.patch(f"/api/schedules/{schedule['id']}", json={"time": "20:00"}).json()
    new_york = api.patch(
        f"/api/schedules/{schedule['id']}", json={"timezone": "America/New_York"}
    ).json()

    # 20:00 in Paris is 18:00 UTC; 20:00 in New York (still on summer time) is 00:00 UTC next day.
    assert (evening["time"], parse(evening["next_run_at"])) == ("20:00", utc(24, 18))
    assert (new_york["timezone"], parse(new_york["next_run_at"])) == (
        "America/New_York",
        utc(25, 0),
    )


def test_the_same_change_twice_leaves_the_same_state(api: TestClient, pipeline: Pipeline) -> None:
    schedule = create(api, pipeline)
    change = {"frequency": "weekly", "weekday": 2, "time": "18:30", "input": "again"}

    once = api.patch(f"/api/schedules/{schedule['id']}", json=change).json()
    twice = api.patch(f"/api/schedules/{schedule['id']}", json=change).json()

    assert once == twice
    assert (once["frequency"], once["weekday"], once["time"]) == ("weekly", 2, "18:30")
    assert parse(once["next_run_at"]) == utc(28, 17, 30)  # Wednesday 18:30 in Paris
    assert api.patch(f"/api/schedules/{schedule['id']}", json={}).json() == once


def test_turning_a_schedule_off_and_on(api: TestClient, pipeline: Pipeline, clock: Clock) -> None:
    schedule = create(api, pipeline)
    url = f"/api/schedules/{schedule['id']}"

    off = api.patch(url, json={"enabled": False}).json()
    assert (off["enabled"], off["next_run_at"]) == (False, None)
    assert api.patch(url, json={"enabled": False}).json() == off

    clock.advance(days=3)
    on = api.patch(url, json={"enabled": True}).json()
    assert on["enabled"] is True
    assert parse(on["next_run_at"]) == utc(28, 8)  # from the clock now, not from before
    assert api.patch(url, json={"enabled": True}).json() == on


def test_a_schedule_whose_inputs_no_longer_fit_can_still_be_turned_off(
    api: TestClient, session: Session, pipeline: Pipeline
) -> None:
    schedule = create(api, pipeline)
    url = f"/api/schedules/{schedule['id']}"
    topic = {"name": "topic", "label": "", "description": ""}
    pipelines.replace_steps(session, pipeline, pipelines.PipelineChanges(inputs=[topic]))

    assert api.patch(url, json={"enabled": False}).status_code == 200
    # Turning it back on checks the inputs again, until they are fixed in the same edit.
    refused = api.patch(url, json={"enabled": True})
    assert refused.status_code == 400
    assert "named inputs instead of text" in refused.json()["detail"]
    fixed = api.patch(url, json={"enabled": True, "inputs": {"topic": "bees"}})
    assert fixed.status_code == 200
    assert (fixed.json()["inputs"], fixed.json()["input"]) == ({"topic": "bees"}, "")


def test_new_inputs_replace_the_old_ones_whole(api: TestClient, pipeline: Pipeline) -> None:
    schedule = create(api, pipeline)

    changed = api.patch(f"/api/schedules/{schedule['id']}", json={"input": "  new  "}).json()

    assert (changed["input"], changed["inputs"]) == ("new", {})
    blank = api.patch(f"/api/schedules/{schedule['id']}", json={"input": " "})
    assert blank.status_code == 400
    assert "must not be blank" in blank.json()["detail"]


def test_a_due_time_is_kept_when_only_the_inputs_change(
    api: TestClient, pipeline: Pipeline, clock: Clock
) -> None:
    schedule = create(api, pipeline)
    clock.advance(days=1)  # 12:00 on the 25th: the 08:00 time is due

    changed = api.patch(f"/api/schedules/{schedule['id']}", json={"input": "other"}).json()

    assert parse(changed["next_run_at"]) == utc(25, 8)


@pytest.mark.parametrize(
    "change",
    [
        {"time": "25:00"},
        {"timezone": "Nowhere"},
        {"frequency": "weekly"},
        {"frequency": "monthly"},
        {"weekday": 9},
        {"day_of_month": 99},
    ],
)
def test_an_invalid_change_is_refused_and_changes_nothing(
    api: TestClient, pipeline: Pipeline, change: dict[str, Any]
) -> None:
    schedule = create(api, pipeline)

    response = api.patch(f"/api/schedules/{schedule['id']}", json=change)

    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"
    assert listing(api) == [schedule]


# --- delete and ownership ---------------------------------------------------------


def test_deleting_a_schedule_keeps_its_runs_in_the_history(
    api: TestClient, pipeline: Pipeline
) -> None:
    schedule = create(api, pipeline)
    run = api.post(f"/api/schedules/{schedule['id']}/run").json()

    assert api.delete(f"/api/schedules/{schedule['id']}").status_code == 204

    assert listing(api) == []
    kept = api.get(f"/api/runs/{run['id']}").json()
    assert (kept["trigger"], kept["schedule_id"]) == ("schedule", None)
    again = api.delete(f"/api/schedules/{schedule['id']}")
    assert (again.status_code, again.json()["error"]) == (404, "not_found")


def test_deleting_a_pipeline_deletes_its_schedules(api: TestClient, pipeline: Pipeline) -> None:
    create(api, pipeline)
    create(api, pipeline, time="10:00")

    assert api.delete(f"/api/pipelines/{pipeline.id}/").status_code == 204

    assert listing(api) == []


def test_another_accounts_schedule_is_a_404_on_every_route(
    api: TestClient, session: Session, stranger: User
) -> None:
    theirs = make_pipeline(session, stranger, "Theirs")
    schedule = api.post(
        "/api/schedules", json=body(theirs), headers=bearer(stranger)
    ).json()  # as the stranger

    for method, path, payload in (
        ("PATCH", f"/api/schedules/{schedule['id']}", {"enabled": False}),
        ("DELETE", f"/api/schedules/{schedule['id']}", None),
        ("POST", f"/api/schedules/{schedule['id']}/run", None),
    ):
        response = api.request(method, path, json=payload)
        assert (response.status_code, response.json()["error"]) == (404, "not_found"), path
    assert listing(api) == []
    assert listing(api, pipeline_id=theirs.id) == []


# --- run now ----------------------------------------------------------------------


def test_run_now_starts_a_run_of_the_schedule_and_leaves_its_timing_alone(
    api: TestClient, pipeline: Pipeline
) -> None:
    schedule = create(api, pipeline)

    response = api.post(f"/api/schedules/{schedule['id']}/run")

    assert response.status_code == 202
    started = response.json()
    assert (started["trigger"], started["schedule_id"]) == ("schedule", schedule["id"])
    assert (started["pipeline_id"], started["input"]) == (pipeline.id, "go")
    run = api.get(f"/api/runs/{started['id']}").json()
    assert (run["status"], run["final_output"]) == ("succeeded", "fake reply")
    [after] = listing(api)
    assert after["next_run_at"] == schedule["next_run_at"]
    assert after["last_run"]["id"] == started["id"]
    assert after["last_run"]["status"] == "succeeded"
    # A second press is a second run, and the newest is the schedule's last.
    second = api.post(f"/api/schedules/{schedule['id']}/run").json()
    assert listing(api)[0]["last_run"]["id"] == second["id"] != started["id"]


def test_run_now_works_for_a_schedule_that_is_off(api: TestClient, pipeline: Pipeline) -> None:
    schedule = create(api, pipeline, enabled=False)

    started = api.post(f"/api/schedules/{schedule['id']}/run")

    assert started.status_code == 202
    assert listing(api)[0]["next_run_at"] is None


def test_a_run_now_that_fails_is_a_failed_run_like_any_other(
    app: FastAPI, api: TestClient, pipeline: Pipeline
) -> None:
    schedule = create(api, pipeline)
    use_pipeline_generator(app, FailingProvider(llm_exceptions.ProviderTimeout("slow")))

    started = api.post(f"/api/schedules/{schedule['id']}/run")

    assert started.status_code == 202
    run = api.get(f"/api/runs/{started.json()['id']}").json()
    assert (run["status"], run["error"]["code"]) == ("failed", "provider_timeout")
    assert listing(api)[0]["last_run"]["status"] == "failed"


def test_run_now_refuses_inputs_the_pipeline_no_longer_takes(
    api: TestClient, session: Session, pipeline: Pipeline
) -> None:
    schedule = create(api, pipeline)
    topic = {"name": "topic", "label": "", "description": ""}
    pipelines.replace_steps(session, pipeline, pipelines.PipelineChanges(inputs=[topic]))

    response = api.post(f"/api/schedules/{schedule['id']}/run")

    assert response.status_code == 400
    assert "named inputs instead of text" in response.json()["detail"]
    assert api.get("/api/runs").json()["total"] == 0


# --- preview ----------------------------------------------------------------------


def test_a_timing_can_be_previewed_without_saving_anything(api: TestClient) -> None:
    timing = {"frequency": "weekly", "weekday": 0, "time": "09:00", "timezone": PARIS}

    response = api.post("/api/schedules/preview", json=timing)

    assert response.status_code == 200
    assert parse(response.json()["next_run_at"]) == utc(26, 8)
    assert listing(api) == []


def test_a_preview_applies_the_same_rules_as_saving(api: TestClient) -> None:
    unknown = api.post(
        "/api/schedules/preview",
        json={"frequency": "daily", "time": "09:00", "timezone": "Mars/Olympus"},
    )
    no_weekday = api.post(
        "/api/schedules/preview",
        json={"frequency": "weekly", "time": "09:00", "timezone": PARIS},
    )

    assert unknown.status_code == no_weekday.status_code == 400
    assert "Unknown time zone" in unknown.json()["detail"]
    assert "day of the week" in no_weekday.json()["detail"]


# --- what the run history shows ----------------------------------------------------


def test_the_run_history_says_what_started_each_run(api: TestClient, pipeline: Pipeline) -> None:
    manual = api.post(f"/api/pipelines/{pipeline.id}/runs", json={"input": "hi"}).json()
    schedule = create(api, pipeline)
    scheduled = api.post(f"/api/schedules/{schedule['id']}/run").json()

    items = {item["id"]: item for item in api.get("/api/runs").json()["items"]}

    assert (items[manual["id"]]["trigger"], items[manual["id"]]["schedule_id"]) == ("manual", None)
    assert (items[scheduled["id"]]["trigger"], items[scheduled["id"]]["schedule_id"]) == (
        "schedule",
        schedule["id"],
    )
    assert api.get(f"/api/runs/{scheduled['id']}").json()["trigger"] == "schedule"


def test_what_went_wrong_at_a_scheduled_time_is_listed(
    app: FastAPI, api: TestClient, pipeline: Pipeline
) -> None:
    schedule = create(api, pipeline)
    with app.state.database.session() as db:
        repository.set_last_error(db, schedule["id"], "No API key is set for openrouter.")

    assert listing(api)[0]["last_error"] == "No API key is set for openrouter."


def test_the_time_a_schedule_is_created_at_is_the_requests_now(
    api: TestClient, pipeline: Pipeline, clock: Clock
) -> None:
    clock.now = NOW + timedelta(days=10)  # Tuesday 3 Nov

    created = create(api, pipeline)

    assert parse(created["next_run_at"]) == utc(4, 8, month=11)
