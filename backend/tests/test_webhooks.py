"""Webhooks: a workflow's secret link, made and switched by chat, read only by its
owner, and called by another app to start a run as the owner."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.tools import BaseTool, ToolException
from sqlalchemy.orm import Session

from api.deps import webhook_calls
from api.exceptions import ValidationFailed
from api.models import Pipeline, Run, RunTrigger, User, Webhook
from api.repositories import pipelines, users
from api.repositories.pipelines import PipelineChanges
from api.schemas.common import RUN_INPUT_MAX_LENGTH
from api.security import hash_password
from api.services.catalog import default_model_id
from api.services.chat_events import tool_finished
from api.services.chat_tools.webhooks import webhook_tools
from api.services.runs import RunService
from api.services.webhooks.calls import CallPolicy, WebhookCalls
from api.services.webhooks.inputs import call_start
from config.logging_setup import WebhookTokenFilter
from tests.chat_fakes import by_name, chat_scope
from tests.conftest import TEST_SETTINGS, FakeProvider, InlineRunExecutor, bearer

TOPIC = {"name": "topic", "label": "Topic", "description": ""}
TONE = {"name": "tone", "label": "Tone", "description": ""}
FUN = {**TONE, "default_value": "fun"}


def workflow(session: Session, owner: User, inputs: list[dict[str, str]] | None = None) -> Pipeline:
    step = {"order": 1, "stage": 1, "title": "Digest", "prompt": "Write about {input}"}
    steps = [{**step, "model": default_model_id()}]
    return pipelines.create_with_steps(
        session, owner, PipelineChanges("Digest", inputs=inputs or [], steps=steps)
    )


def tools(app: FastAPI, user: User) -> dict[str, BaseTool]:
    return by_name(webhook_tools(chat_scope(app, user)))


def use_calls(app: FastAPI, max_calls: int = 60) -> FakeProvider:
    """Webhook calls whose runs finish inline, on a fake agent instead of the owner's key."""
    agent = FakeProvider(reply="the digest")
    runs = RunService(app.state.database, InlineRunExecutor(), max_parallel_steps=1)
    policy = CallPolicy(TEST_SETTINGS.secret_key, max_calls, 3600)
    calls = WebhookCalls(app.state.database, runs, lambda session, owner: agent, policy)
    app.dependency_overrides[webhook_calls] = lambda: calls
    return agent


def link(client: TestClient, owner: User, webhook_id: int) -> str:
    """The token its owner's screen reads, and the path another app calls."""
    response = client.get(f"/api/webhooks/{webhook_id}", headers=bearer(owner))
    assert response.status_code == 200
    token: str = response.json()["token"]
    return f"/api/hooks/{token}"


def test_a_workflow_gets_one_secret_link_that_only_its_owner_reads(
    app: FastAPI, client: TestClient, session: Session, user: User
) -> None:
    pipeline = workflow(session, user)
    made = tools(app, user)["create_webhook"].invoke({"pipeline_id": pipeline.id})
    again = tools(app, user)["create_webhook"].invoke({"pipeline_id": pipeline.id})

    response = client.get(f"/api/webhooks/{made['id']}", headers=bearer(user))

    assert made == again
    assert made["workflow"] == "Digest" and made["on"] is True
    token = response.json()["token"]
    assert len(token) >= 43
    assert token not in json.dumps(made)  # the chat's model never reads the link
    stored = session.get(Webhook, made["id"])
    assert stored is not None
    assert stored.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in stored.token_encrypted
    assert tool_finished("create_webhook", made).action == {
        "kind": "webhook",
        "id": made["id"],
        "title": "Digest",
        "subtitle": "Webhook on",
    }


def test_another_app_starts_a_run_as_the_owner_by_calling_the_link(
    app: FastAPI, client: TestClient, session: Session, user: User
) -> None:
    agent = use_calls(app)
    made = tools(app, user)["create_webhook"].invoke({"pipeline_id": workflow(session, user).id})
    path = link(client, user, made["id"])

    response = client.post(path, content="Bees in winter", headers={"content-type": "text/plain"})

    assert response.status_code == 202
    run = session.get(Run, response.json()["run_id"])
    assert run is not None
    assert response.json()["status"] == "queued"
    assert (run.trigger, run.user_id) == (RunTrigger.WEBHOOK, user.id)
    assert agent.calls == [("Write about Bees in winter", default_model_id())]
    listed = tools(app, user)["list_webhooks"].invoke({})
    assert listed[0]["last_called_at"] is not None and listed[0]["last_error"] is None


def test_an_unknown_or_switched_off_link_starts_nothing(
    app: FastAPI, client: TestClient, session: Session, user: User
) -> None:
    use_calls(app)
    made = tools(app, user)["create_webhook"].invoke({"pipeline_id": workflow(session, user).id})
    path = link(client, user, made["id"])

    assert client.post("/api/hooks/not-a-real-token", content="x").status_code == 404
    off = tools(app, user)["set_webhook"].invoke({"webhook_id": made["id"], "on": False})
    assert (off["on"], tool_finished("set_webhook", off).action["subtitle"]) == (  # type: ignore[index]
        False,
        "Webhook off",
    )
    switched_off = client.post(path, content="x")
    assert (switched_off.status_code, switched_off.json()["error"]) == (404, "not_found")
    tools(app, user)["set_webhook"].invoke({"webhook_id": made["id"], "on": True})
    assert client.post(path, content="x").status_code == 202


def test_a_renewed_link_replaces_the_old_one(
    app: FastAPI, client: TestClient, session: Session, user: User
) -> None:
    use_calls(app)
    made = tools(app, user)["create_webhook"].invoke({"pipeline_id": workflow(session, user).id})
    old = link(client, user, made["id"])

    tools(app, user)["renew_webhook_link"].invoke({"webhook_id": made["id"]})
    new = link(client, user, made["id"])

    assert new != old
    assert client.post(old, content="x").status_code == 404
    assert client.post(new, content="x").status_code == 202


def test_calls_past_the_allowance_are_throttled(
    app: FastAPI, client: TestClient, session: Session, user: User
) -> None:
    use_calls(app, max_calls=2)
    made = tools(app, user)["create_webhook"].invoke({"pipeline_id": workflow(session, user).id})
    path = link(client, user, made["id"])

    statuses = [client.post(path, content="x").status_code for _ in range(3)]

    assert statuses == [202, 202, 429]


def test_a_refused_call_is_explained_and_kept_on_the_webhook(
    app: FastAPI, client: TestClient, session: Session, user: User
) -> None:
    use_calls(app)
    pipeline = workflow(session, user, inputs=[TOPIC, TONE])
    made = tools(app, user)["create_webhook"].invoke({"pipeline_id": pipeline.id})

    response = client.post(link(client, user, made["id"]), content="just text")

    assert (response.status_code, response.json()["error"]) == (400, "validation_error")
    assert "topic, tone" in response.json()["detail"]
    assert "topic, tone" in tools(app, user)["list_webhooks"].invoke({})[0]["last_error"]
    assert session.query(Run).count() == 0


def test_another_persons_webhook_cannot_be_read_or_switched(
    app: FastAPI, client: TestClient, session: Session, user: User
) -> None:
    stranger = users.create(session, "stranger", hash_password("password-123", 1))
    theirs = tools(app, stranger)["create_webhook"].invoke(
        {"pipeline_id": workflow(session, stranger).id}
    )

    assert client.get(f"/api/webhooks/{theirs['id']}", headers=bearer(user)).status_code == 404
    with pytest.raises(ToolException, match="not found"):
        tools(app, user)["set_webhook"].invoke({"webhook_id": theirs["id"], "on": False})
    with pytest.raises(ToolException, match="not found"):
        tools(app, user)["create_webhook"].invoke({"pipeline_id": theirs["id"]})
    assert tools(app, user)["list_webhooks"].invoke({}) == []


def test_deleting_the_workflow_deletes_its_webhook(
    app: FastAPI, session: Session, user: User
) -> None:
    pipeline = workflow(session, user)
    made = tools(app, user)["create_webhook"].invoke({"pipeline_id": pipeline.id})

    pipelines.delete(session, pipeline)

    session.expire_all()
    assert session.get(Webhook, made["id"]) is None


@pytest.mark.parametrize(
    ("fields", "body", "text", "values"),
    [
        ([], b"Bees in winter", "Bees in winter", {}),
        ([], b'{"title": "Bees"}', '{\n  "title": "Bees"\n}', {}),
        ([], b'{"input": "  Bees  "}', "Bees", {}),
        ([TOPIC], b'{"inputs": {"topic": "bees"}}', "", {"topic": "bees"}),
        (
            [TOPIC, TONE],
            b'{"topic": "bees", "tone": 3, "x": 1}',
            "",
            {"topic": "bees", "tone": "3"},
        ),
        ([TOPIC], b"bees", "", {"topic": "bees"}),
        ([TOPIC], b'{"subject": "bees"}', "", {"topic": '{\n  "subject": "bees"\n}'}),
        # An input the call does not send takes its declared default.
        ([TOPIC, FUN], b'{"topic": "bees", "tone": " "}', "", {"topic": "bees", "tone": "fun"}),
        (
            [{**TOPIC, "default_value": "cars"}, FUN],
            b'{"form": 1}',
            "",
            {"topic": "cars", "tone": "fun"},
        ),
    ],
)
def test_what_a_call_sends_becomes_the_runs_input(
    fields: list[dict[str, str]], body: bytes, text: str, values: dict[str, str]
) -> None:
    start = call_start(fields, body)

    assert (start.text, dict(start.values), start.trigger) == (text, values, RunTrigger.WEBHOOK)


@pytest.mark.parametrize(
    ("fields", "body"),
    [
        ([TOPIC, TONE], b"just text"),
        ([], b'{"input": 5}'),
        ([], b"x" * (RUN_INPUT_MAX_LENGTH + 1)),
    ],
)
def test_a_call_that_cannot_become_a_run_is_refused(
    fields: list[dict[str, str]], body: bytes
) -> None:
    with pytest.raises(ValidationFailed):
        call_start(fields, body)


def test_the_access_log_never_shows_a_webhook_link() -> None:
    args: Any = ("1.2.3.4:5", "POST", "/api/hooks/s3cr3t-T0ken?ref=form", "1.1", 202)
    line = '%s - "%s %s" %s %d'
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, line, args, None)

    WebhookTokenFilter().filter(record)

    assert "s3cr3t" not in record.getMessage()
    assert "/api/hooks/<token>?ref=form" in record.getMessage()
