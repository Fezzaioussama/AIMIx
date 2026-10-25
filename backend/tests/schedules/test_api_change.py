"""Changing schedules over HTTP (PATCH): the next run is worked out again, turning off and on,
inputs checked again, a due time kept, and the reason a time failed cleared by a real edit."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.models import Pipeline
from api.repositories import pipelines
from api.repositories import schedules as repository
from tests.schedules.support import Clock, create_schedule, listing, parse, when


def test_changing_the_time_works_out_the_next_run_again(
    api: TestClient, pipeline: Pipeline
) -> None:
    schedule = create_schedule(api, pipeline)

    evening = api.patch(f"/api/schedules/{schedule['id']}", json={"time": "20:00"}).json()
    new_york = api.patch(
        f"/api/schedules/{schedule['id']}", json={"timezone": "America/New_York"}
    ).json()

    # 20:00 in Paris is 18:00 UTC; 20:00 in New York (still on summer time) is 00:00 UTC next day.
    assert (evening["time"], parse(evening["next_run_at"])) == ("20:00", when(24, 18))
    assert (new_york["timezone"], parse(new_york["next_run_at"])) == (
        "America/New_York",
        when(25, 0),
    )


def test_the_same_change_twice_leaves_the_same_state(api: TestClient, pipeline: Pipeline) -> None:
    schedule = create_schedule(api, pipeline)
    change = {"frequency": "weekly", "weekday": 2, "time": "18:30", "input": "again"}

    once = api.patch(f"/api/schedules/{schedule['id']}", json=change).json()
    twice = api.patch(f"/api/schedules/{schedule['id']}", json=change).json()

    assert once == twice
    assert (once["frequency"], once["weekday"], once["time"]) == ("weekly", 2, "18:30")
    assert parse(once["next_run_at"]) == when(28, 17, 30)  # Wednesday 18:30 in Paris
    assert api.patch(f"/api/schedules/{schedule['id']}", json={}).json() == once


def test_turning_a_schedule_off_and_on(api: TestClient, pipeline: Pipeline, clock: Clock) -> None:
    schedule = create_schedule(api, pipeline)
    url = f"/api/schedules/{schedule['id']}"

    off = api.patch(url, json={"enabled": False}).json()
    assert (off["enabled"], off["next_run_at"]) == (False, None)
    assert api.patch(url, json={"enabled": False}).json() == off

    clock.advance(days=3)
    on = api.patch(url, json={"enabled": True}).json()
    assert on["enabled"] is True
    assert parse(on["next_run_at"]) == when(28, 8)  # from the clock now, not from before
    assert api.patch(url, json={"enabled": True}).json() == on


def test_a_schedule_whose_inputs_no_longer_fit_can_still_be_turned_off(
    api: TestClient, session: Session, pipeline: Pipeline
) -> None:
    schedule = create_schedule(api, pipeline)
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
    schedule = create_schedule(api, pipeline)

    changed = api.patch(f"/api/schedules/{schedule['id']}", json={"input": "  new  "}).json()

    assert (changed["input"], changed["inputs"]) == ("new", {})
    blank = api.patch(f"/api/schedules/{schedule['id']}", json={"input": " "})
    assert blank.status_code == 400
    assert "must not be blank" in blank.json()["detail"]


def test_a_due_time_is_kept_when_only_the_inputs_change(
    api: TestClient, pipeline: Pipeline, clock: Clock
) -> None:
    schedule = create_schedule(api, pipeline)
    clock.advance(days=1)  # 12:00 on the 25th: the 08:00 time is due

    changed = api.patch(f"/api/schedules/{schedule['id']}", json={"input": "other"}).json()

    assert parse(changed["next_run_at"]) == when(25, 8)


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
    schedule = create_schedule(api, pipeline)

    response = api.patch(f"/api/schedules/{schedule['id']}", json=change)

    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"
    assert listing(api) == [schedule]


@pytest.mark.parametrize(
    "change",
    [{"input": "a new brief"}, {"time": "20:00"}, {"timezone": "Asia/Tokyo"}, {"enabled": True}],
)
def test_an_edit_that_changes_what_a_schedule_runs_clears_why_it_last_failed(
    app: FastAPI, api: TestClient, pipeline: Pipeline, change: dict[str, Any]
) -> None:
    schedule = create_schedule(api, pipeline)
    url = f"/api/schedules/{schedule['id']}"
    with app.state.database.session() as db:
        repository.set_last_error(db, schedule["id"], "No API key is set for openrouter.")
    # Turning it off is not a fix, so the reason stays (and a turn-on below starts from off).
    assert api.patch(url, json={"enabled": False}).json()["last_error"] == (
        "No API key is set for openrouter."
    )

    fixed = api.patch(url, json=change).json()
    again = api.patch(url, json=change).json()

    assert fixed["last_error"] is None
    assert again == fixed


def test_an_edit_that_changes_nothing_keeps_why_it_last_failed(
    app: FastAPI, api: TestClient, pipeline: Pipeline
) -> None:
    schedule = create_schedule(api, pipeline)
    with app.state.database.session() as db:
        repository.set_last_error(db, schedule["id"], "No API key is set for openrouter.")

    same = api.patch(f"/api/schedules/{schedule['id']}", json={"time": "09:00"}).json()

    assert same["last_error"] == "No API key is set for openrouter."
