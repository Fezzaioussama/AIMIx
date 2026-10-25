"""A run that asks, over HTTP and end to end: the whole app on a file database, its
runs on the real background executor and its step agents stopping at the gate."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.deps import pipeline_agent_factory
from api.main import create_app
from api.models import Base, Pipeline
from config.settings import pin_settings
from tests.approval_fakes import AskingAgent, make_owner, make_pipeline
from tests.conftest import TEST_SETTINGS, bearer
from tests.test_runs_service import WAIT_SECONDS


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[TestClient, Pipeline]]:
    """The whole app on a file database, its runs on the real executor, its step
    agents stopping at the gate."""
    pin_settings(
        TEST_SETTINGS.model_copy(update={"database_url": f"sqlite:///{tmp_path / 'app.sqlite3'}"})
    )
    try:
        app = create_app()
        Base.metadata.create_all(app.state.database.engine)
        mine = make_owner(app.state.database, "http-owner")
        pipeline = make_pipeline(app.state.database, mine)
        agent = AskingAgent(app.state.database)
        app.dependency_overrides[pipeline_agent_factory] = lambda: lambda: agent
        with TestClient(app) as client:
            client.headers.update(bearer(mine))
            yield client, pipeline
    finally:
        pin_settings(TEST_SETTINGS)


def poll(client: TestClient, run_id: int, done: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    """The run as the API shows it, once ``done`` says so."""
    deadline = time.monotonic() + WAIT_SECONDS
    body: dict[str, Any] = {}
    while time.monotonic() < deadline:
        body = client.get(f"/api/runs/{run_id}").json()
        if done(body):
            return body
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} never got there: {body.get('status')}")


@pytest.mark.parametrize(
    ("answer_to_give", "reported"), [("approve", "answer-approved"), ("decline", "answer-declined")]
)
def test_the_whole_flow_over_http(
    served: tuple[TestClient, Pipeline], answer_to_give: str, reported: str
) -> None:
    client, pipeline = served
    run_id = client.post(f"/api/pipelines/{pipeline.id}/runs", json={"input": "go"}).json()["id"]

    waiting = poll(client, run_id, lambda body: body["status"] == "waiting")
    [asked] = waiting["pending_approvals"]
    assert client.get("/api/runs", params={"status": "waiting"}).json()["total"] == 1
    answered = client.post(f"/api/runs/{run_id}/approvals/{asked['id']}/{answer_to_give}")

    assert answered.status_code == 200
    done = poll(client, run_id, lambda body: body["status"] == "succeeded")
    assert done["final_output"] == reported
    assert done["pending_approvals"] == []
    assert client.get("/api/runs", params={"status": "waiting"}).json() == {"items": [], "total": 0}
