"""What else a schedule can do over HTTP: be deleted, run now, be previewed, show up in the run
history and show why a time failed; and that every route is scoped to its owner."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.models import Pipeline, User
from api.repositories import pipelines
from api.repositories import schedules as repository
from llm import exceptions as llm_exceptions
from tests.conftest import FailingProvider, bearer, use_pipeline_generator
from tests.schedules.support import PARIS, body, create_schedule, listing, parse, when
from tests.test_endpoints import make_pipeline


def test_deleting_a_schedule_keeps_its_runs_in_the_history(
    api: TestClient, pipeline: Pipeline
) -> None:
    schedule = create_schedule(api, pipeline)
    run = api.post(f"/api/schedules/{schedule['id']}/run").json()

    assert api.delete(f"/api/schedules/{schedule['id']}").status_code == 204

    assert listing(api) == []
    kept = api.get(f"/api/runs/{run['id']}").json()
    assert (kept["trigger"], kept["schedule_id"]) == ("schedule", None)
    again = api.delete(f"/api/schedules/{schedule['id']}")
    assert (again.status_code, again.json()["error"]) == (404, "not_found")


def test_deleting_a_pipeline_deletes_its_schedules(api: TestClient, pipeline: Pipeline) -> None:
    create_schedule(api, pipeline)
    create_schedule(api, pipeline, time="10:00")

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


def test_run_now_starts_a_run_of_the_schedule_and_leaves_its_timing_alone(
    api: TestClient, pipeline: Pipeline
) -> None:
    schedule = create_schedule(api, pipeline)

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
    schedule = create_schedule(api, pipeline, enabled=False)

    started = api.post(f"/api/schedules/{schedule['id']}/run")

    assert started.status_code == 202
    assert listing(api)[0]["next_run_at"] is None


def test_a_run_now_that_fails_is_a_failed_run_like_any_other(
    app: FastAPI, api: TestClient, pipeline: Pipeline
) -> None:
    schedule = create_schedule(api, pipeline)
    use_pipeline_generator(app, FailingProvider(llm_exceptions.ProviderTimeout("slow")))

    started = api.post(f"/api/schedules/{schedule['id']}/run")

    assert started.status_code == 202
    run = api.get(f"/api/runs/{started.json()['id']}").json()
    assert (run["status"], run["error"]["code"]) == ("failed", "provider_timeout")
    assert listing(api)[0]["last_run"]["status"] == "failed"


def test_run_now_refuses_inputs_the_pipeline_no_longer_takes(
    api: TestClient, session: Session, pipeline: Pipeline
) -> None:
    schedule = create_schedule(api, pipeline)
    topic = {"name": "topic", "label": "", "description": ""}
    pipelines.replace_steps(session, pipeline, pipelines.PipelineChanges(inputs=[topic]))

    response = api.post(f"/api/schedules/{schedule['id']}/run")

    assert response.status_code == 400
    assert "named inputs instead of text" in response.json()["detail"]
    assert api.get("/api/runs").json()["total"] == 0


def test_a_timing_can_be_previewed_without_saving_anything(api: TestClient) -> None:
    timing = {"frequency": "weekly", "weekday": 0, "time": "09:00", "timezone": PARIS}

    response = api.post("/api/schedules/preview", json=timing)

    assert response.status_code == 200
    assert parse(response.json()["next_run_at"]) == when(26, 8)
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


def test_the_run_history_says_what_started_each_run(api: TestClient, pipeline: Pipeline) -> None:
    manual = api.post(f"/api/pipelines/{pipeline.id}/runs", json={"input": "hi"}).json()
    schedule = create_schedule(api, pipeline)
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
    schedule = create_schedule(api, pipeline)
    with app.state.database.session() as db:
        repository.set_last_error(db, schedule["id"], "No API key is set for openrouter.")

    assert listing(api)[0]["last_error"] == "No API key is set for openrouter."
