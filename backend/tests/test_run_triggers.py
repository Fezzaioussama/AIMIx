"""What started a run is recorded: its owner by hand or through the API, a
schedule, or the chat agent (the schedule side is in test_scheduler.py)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.models import Pipeline, Run, RunTrigger, User
from api.repositories import pipelines
from tests.conftest import FakeProvider
from tests.test_agent_tools import chat_tools, one_step
from tests.test_endpoints import make_pipeline


def triggers(session: Session) -> list[RunTrigger]:
    session.expire_all()
    return [run.trigger for run in session.query(Run).order_by(Run.id)]


def test_a_run_started_from_chat_is_marked_as_chat(
    app: FastAPI, session: Session, user: User
) -> None:
    saved = pipelines.create_with_steps(session, user, one_step("Echo", "{input}"))
    run = chat_tools(app, user, FakeProvider())["run_pipeline"]

    run.invoke({"pipeline_id": saved.id, "input_text": "hello"})

    only = session.query(Run).one()
    assert (only.trigger, only.schedule_id) == (RunTrigger.CHAT, None)


def test_runs_started_through_the_api_are_marked_manual(
    auth_client: TestClient, session: Session, user: User, fake_provider: FakeProvider
) -> None:
    pipeline: Pipeline = make_pipeline(session, user, "Digest")

    auth_client.post(f"/api/pipelines/{pipeline.id}/runs", json={"input": "a"})
    auth_client.post(f"/api/pipelines/{pipeline.id}/run", json={"input": "b"})

    assert triggers(session) == [RunTrigger.MANUAL, RunTrigger.MANUAL]


def test_a_resumed_run_keeps_what_started_it(
    auth_client: TestClient, session: Session, user: User, fake_provider: FakeProvider
) -> None:
    pipeline = make_pipeline(session, user, "Digest")
    started = auth_client.post(f"/api/pipelines/{pipeline.id}/runs", json={"input": "a"}).json()

    auth_client.post(f"/api/runs/{started['id']}/resume")

    assert triggers(session) == [RunTrigger.MANUAL]
