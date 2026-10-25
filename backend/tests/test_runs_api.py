"""HTTP surface of pipeline runs: start, poll, list, stop, resume and delete,
scoped to their owner. Runs execute inline here (conftest.InlineRunExecutor)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.models import Pipeline, Run, RunStatus, StepStatus, User
from api.repositories import runs, users
from api.security import hash_password
from llm import exceptions as llm_exceptions
from tests.conftest import FailingProvider, FakeProvider, bearer, use_pipeline_generator
from tests.test_endpoints import make_pipeline

SUMMARY_KEYS = {
    "id",
    "pipeline_id",
    "pipeline_name",
    "trigger",
    "schedule_id",
    "status",
    "error",
    "created_at",
    "started_at",
    "finished_at",
    "max_cost_usd",
    "max_tokens",
    "usage",
}


def start(client: TestClient, pipeline: Pipeline, text: str = "seed") -> dict[str, Any]:
    response = client.post(f"/api/pipelines/{pipeline.id}/runs", json={"input": text})
    assert response.status_code == 202, response.text
    body: dict[str, Any] = response.json()
    return body


def make_active(session: Session, run_id: int) -> None:
    """As if the run were still executing: running, its first step too."""
    runs.set_status(session, run_id, list(RunStatus), {"status": RunStatus.RUNNING})
    running = {"status": StepStatus.RUNNING}
    runs.set_step(session, run_id, runs.StepChange(1, frozenset(StepStatus), running))


def test_starting_a_run_returns_202_and_the_run_can_be_polled(
    auth_client: TestClient, user: User, session: Session, fake_provider: FakeProvider
) -> None:
    pipeline = make_pipeline(session, user, "Runner", steps=2)

    body = start(auth_client, pipeline)

    assert body["pipeline_id"] == pipeline.id
    assert body["pipeline_name"] == "Runner"
    assert (body["input"], body["inputs"]) == ("seed", {})
    assert body["definition"]["steps"][0]["prompt"] == "s1 {input}"
    polled = auth_client.get(f"/api/runs/{body['id']}").json()
    assert polled["status"] == "succeeded"
    assert polled["final_output"] == "fake reply"
    assert polled["error"] is None
    assert polled["created_at"].endswith(("Z", "+00:00"))
    assert [step["status"] for step in polled["steps"]] == ["succeeded", "succeeded"]
    assert [step["is_output"] for step in polled["steps"]] == [False, True]
    assert polled["steps"][1]["input_used"] == "fake reply"


def test_invalid_inputs_are_a_400_and_save_no_run(
    auth_client: TestClient, user: User, session: Session, fake_provider: FakeProvider
) -> None:
    pipeline = make_pipeline(session, user, "Runner")

    response = auth_client.post(f"/api/pipelines/{pipeline.id}/runs", json={"input": "  "})

    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"
    assert auth_client.get("/api/runs").json() == {"items": [], "total": 0}


def test_a_failed_run_reports_its_error_and_can_be_resumed(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    pipeline = make_pipeline(session, user, "Flaky", steps=2)
    use_pipeline_generator(app, FailingProvider(llm_exceptions.ProviderTimeout("slow")))
    failed = auth_client.get(f"/api/runs/{start(auth_client, pipeline)['id']}").json()
    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "provider_timeout"
    assert [step["status"] for step in failed["steps"]] == ["failed", "pending"]
    assert failed["steps"][0]["error"]["code"] == "provider_timeout"

    provider = FakeProvider(reply="better")
    use_pipeline_generator(app, provider)
    resumed = auth_client.post(f"/api/runs/{failed['id']}/resume")

    assert resumed.status_code == 200
    assert resumed.json()["status"] == "succeeded"
    assert resumed.json()["error"] is None
    assert len(provider.calls) == 2


def test_resuming_a_succeeded_run_changes_nothing(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    pipeline = make_pipeline(session, user, "Done")
    provider = FakeProvider()
    use_pipeline_generator(app, provider)
    run = start(auth_client, pipeline)

    again = auth_client.post(f"/api/runs/{run['id']}/resume").json()

    assert again["status"] == "succeeded"
    assert len(provider.calls) == 1


def test_stopping_an_active_run_is_immediate_and_idempotent(
    auth_client: TestClient, user: User, session: Session, fake_provider: FakeProvider
) -> None:
    pipeline = make_pipeline(session, user, "Long", steps=2)
    run = start(auth_client, pipeline)
    make_active(session, run["id"])

    stopped = auth_client.post(f"/api/runs/{run['id']}/cancel")
    again = auth_client.post(f"/api/runs/{run['id']}/cancel")

    assert stopped.status_code == again.status_code == 200
    assert stopped.json()["status"] == again.json()["status"] == "cancelled"
    assert stopped.json()["steps"][0]["status"] == "cancelled"
    assert stopped.json()["finished_at"] is not None


def test_stopping_a_finished_run_leaves_it_as_it_was(
    auth_client: TestClient, user: User, session: Session, fake_provider: FakeProvider
) -> None:
    pipeline = make_pipeline(session, user, "Done")
    run = start(auth_client, pipeline)

    assert auth_client.post(f"/api/runs/{run['id']}/cancel").json()["status"] == "succeeded"


def test_only_finished_runs_can_be_deleted(
    auth_client: TestClient, user: User, session: Session, fake_provider: FakeProvider
) -> None:
    pipeline = make_pipeline(session, user, "Done")
    finished = start(auth_client, pipeline)
    active = start(auth_client, pipeline)
    make_active(session, active["id"])

    refused = auth_client.delete(f"/api/runs/{active['id']}")
    assert refused.status_code == 409
    assert refused.json()["error"] == "conflict"

    assert auth_client.delete(f"/api/runs/{finished['id']}").status_code == 204
    assert auth_client.get(f"/api/runs/{finished['id']}").status_code == 404


def test_the_history_is_paged_newest_first_and_filters_by_pipeline(
    auth_client: TestClient, user: User, session: Session, fake_provider: FakeProvider
) -> None:
    first = make_pipeline(session, user, "First")
    second = make_pipeline(session, user, "Second")
    ids = [start(auth_client, pipeline)["id"] for pipeline in (first, second, first)]

    page = auth_client.get("/api/runs", params={"limit": 2}).json()
    rest = auth_client.get("/api/runs", params={"limit": 2, "offset": 2}).json()
    only_first = auth_client.get("/api/runs", params={"pipeline_id": first.id}).json()

    assert page["total"] == rest["total"] == 3
    assert [item["id"] for item in page["items"] + rest["items"]] == ids[::-1]
    assert set(page["items"][0]) == SUMMARY_KEYS
    assert [item["id"] for item in only_first["items"]] == [ids[2], ids[0]]
    assert only_first["total"] == 2


def test_a_page_size_out_of_range_is_a_validation_error(auth_client: TestClient) -> None:
    for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
        response = auth_client.get("/api/runs", params=params)
        assert response.status_code == 400, params
        assert response.json()["error"] == "validation_error"


def test_runs_are_scoped_to_their_owner(
    auth_client: TestClient, session: Session, fake_provider: FakeProvider
) -> None:
    stranger = users.create(session, "stranger", hash_password("x-pass-2891", 1))
    theirs = make_pipeline(session, stranger, "Theirs")
    run = auth_client.post(
        f"/api/pipelines/{theirs.id}/runs", json={"input": "go"}, headers=bearer(stranger)
    ).json()

    assert auth_client.get("/api/runs").json()["total"] == 0
    for method, path in (
        ("GET", f"/api/runs/{run['id']}"),
        ("POST", f"/api/runs/{run['id']}/cancel"),
        ("POST", f"/api/runs/{run['id']}/resume"),
        ("DELETE", f"/api/runs/{run['id']}"),
    ):
        response = auth_client.request(method, path)
        assert response.status_code == 404, (method, path)
        assert response.json()["error"] == "not_found"
    started = auth_client.post(f"/api/pipelines/{theirs.id}/runs", json={"input": "x"})
    assert started.status_code == 404


def test_the_synchronous_run_endpoint_is_recorded_too(
    auth_client: TestClient, user: User, session: Session, fake_provider: FakeProvider
) -> None:
    pipeline = make_pipeline(session, user, "Legacy")

    response = auth_client.post(f"/api/pipelines/{pipeline.id}/run", json={"input": "seed"})

    assert response.status_code == 200
    assert response.json()["final_output"] == "fake reply"
    history = auth_client.get("/api/runs").json()
    assert history["total"] == 1
    assert history["items"][0]["status"] == "succeeded"


def test_a_run_outlives_its_pipeline(
    auth_client: TestClient, user: User, session: Session, fake_provider: FakeProvider
) -> None:
    pipeline = make_pipeline(session, user, "Ephemeral")
    run = start(auth_client, pipeline)

    assert auth_client.delete(f"/api/pipelines/{pipeline.id}/").status_code == 204

    kept = auth_client.get(f"/api/runs/{run['id']}").json()
    assert (kept["pipeline_id"], kept["pipeline_name"]) == (None, "Ephemeral")
    assert kept["definition"]["name"] == "Ephemeral"
    session.expire_all()
    assert session.get(Run, run["id"]) is not None
