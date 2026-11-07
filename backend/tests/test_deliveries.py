"""Sending a workflow's results out: an address set by chat, confirmed by its owner's
click, then posted to when a run ends, in the shape its service expects."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.tools import BaseTool, ToolException
from sqlalchemy.orm import Session

from api.exceptions import DeliveryFailed
from api.models import Delivery, Pipeline, Run, RunStatus, User
from api.repositories import pipelines, users
from api.repositories.pipelines import PipelineChanges
from api.security import hash_password, secret_box_for
from api.services.catalog import default_model_id
from api.services.chat_events import tool_finished
from api.services.chat_tools.deliveries import delivery_tools
from api.services.deliveries import service
from api.services.deliveries.formats import (
    DISCORD_TEXT_MAX_CHARS,
    SLACK_TEXT_MAX_CHARS,
    RunMessage,
    body_for,
    kind_of,
)
from api.services.deliveries.sender import Outgoing, ResultDeliveries, SendPolicy, post
from api.services.deliveries.service import DeliveryAccess
from api.services.run_policy import RunPolicy
from api.services.runs import RunService, RunStart
from api.webhook_deps import delivery_sending
from llm import exceptions as llm_exceptions
from tests.chat_fakes import by_name, chat_scope
from tests.conftest import TEST_SETTINGS, FailingProvider, FakeProvider, InlineRunExecutor, bearer

SLACK = "https://hooks.slack.com/services/T000/B000/XyZ9"
BOX = secret_box_for(TEST_SETTINGS)


class Address:
    """A fake address: records what is posted, and answers ``status``."""

    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.posted: list[tuple[str, dict[str, Any]]] = []

    def policy(self, max_chars: int = 20_000) -> SendPolicy:
        def answer(request: httpx.Request) -> httpx.Response:
            self.posted.append((str(request.url), json.loads(request.content)))
            return httpx.Response(self.status)

        return SendPolicy(5, max_chars, transport=lambda: httpx.MockTransport(answer))


def workflow(session: Session, owner: User) -> Pipeline:
    step = {"order": 1, "stage": 1, "title": "Digest", "prompt": "Write about {input}"}
    steps = [{**step, "model": default_model_id()}]
    return pipelines.create_with_steps(session, owner, PipelineChanges("Digest", [], steps))


def tools(app: FastAPI, user: User) -> dict[str, BaseTool]:
    return by_name(delivery_tools(chat_scope(app, user)))


def delivery(session: Session, user: User, confirmed: bool = True, url: str = SLACK) -> int:
    access = DeliveryAccess(session, user, BOX)
    view = service.set_address(access, workflow(session, user).id, url)
    if confirmed:
        asyncio.run(service.confirm(access, view.id, Address().policy()))
    return view.id


def run_with(app: FastAPI, session: Session, address: Address, agent: Any = None) -> Run:
    """A run of the user's only workflow, ended inline, its result sent through ``address``."""
    policy = RunPolicy(deliveries=ResultDeliveries(BOX, address.policy()))
    runs = RunService(app.state.database, InlineRunExecutor(), 1, policy)
    pipeline = session.query(Pipeline).one()
    started = runs.start(pipeline.user, pipeline, RunStart("bees"), agent or FakeProvider("Buzz"))
    return started.run


# --- what each service is sent ------------------------------------------------


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        (SLACK, "slack"),
        ("https://discord.com/api/webhooks/1/abc", "discord"),
        ("https://discord.com/channels/1", "json"),
        ("https://example.com/hooks/aimix", "json"),
    ],
)
def test_the_kind_of_address_is_read_from_its_host(url: str, kind: str) -> None:
    assert kind_of(url) == kind


def test_each_service_gets_the_message_it_expects() -> None:
    message = RunMessage("Digest", "succeeded", "x" * 10_000, run_id=7)

    slack = body_for("slack", message, 50)["text"]
    discord = body_for("discord", message, 50)["content"]
    plain = body_for("json", message, 50)

    assert slack.startswith("Digest finished\n\nxxx") and len(slack) == SLACK_TEXT_MAX_CHARS
    assert len(discord) == DISCORD_TEXT_MAX_CHARS and discord.endswith("…")
    assert plain == {
        "event": "run.ended",
        "run_id": 7,
        "workflow": "Digest",
        "status": "succeeded",
        "result": "x" * 50,
    }


def test_a_private_address_is_refused_by_the_real_transport() -> None:
    with pytest.raises(DeliveryFailed, match="not a public address"):
        asyncio.run(post(SendPolicy(2, 100), Outgoing("https://127.0.0.1/hook", {"text": "hi"})))


# --- set by chat, confirmed by a click -----------------------------------------------


def test_the_chat_sets_an_address_that_sends_nothing_until_confirmed(
    app: FastAPI, client: TestClient, session: Session, user: User
) -> None:
    pipeline = workflow(session, user)

    made = tools(app, user)["send_results_to"].invoke(
        {"pipeline_id": pipeline.id, "address": SLACK}
    )
    card = client.get(f"/api/deliveries/{made['id']}", headers=bearer(user)).json()

    assert made["destination"] == "hooks.slack.com" and made["service"] == "Slack"
    assert (made["confirmed"], made["on"]) == (False, True)
    assert "services/T000" not in json.dumps(made) + json.dumps(card)
    assert (card["hint"], card["confirmed"], card["last_error"]) == ("XyZ9", False, None)
    assert tool_finished("send_results_to", made).action == {
        "kind": "delivery",
        "id": made["id"],
        "title": "Digest",
        "subtitle": "Waiting for your OK",
    }
    stored = session.get(Delivery, made["id"])
    assert stored is not None and SLACK not in stored.url_encrypted


@pytest.mark.parametrize(
    "address", ["http://hooks.slack.com/x", "hooks.slack.com/x", "https://u:p@x.io/"]
)
def test_an_address_that_is_not_plain_https_is_refused(
    app: FastAPI, session: Session, user: User, address: str
) -> None:
    pipeline = workflow(session, user)

    with pytest.raises(ToolException):
        tools(app, user)["send_results_to"].invoke({"pipeline_id": pipeline.id, "address": address})


def test_confirming_posts_a_first_message_then_turns_sending_on(
    app: FastAPI, client: TestClient, session: Session, user: User
) -> None:
    address = Address()
    app.dependency_overrides[delivery_sending] = address.policy
    delivery_id = delivery(session, user, confirmed=False)

    response = client.post(f"/api/deliveries/{delivery_id}/confirm", headers=bearer(user))

    assert response.status_code == 200 and response.json()["confirmed"] is True
    assert address.posted == [(SLACK, {"text": "Digest will send its results here"})]


def test_an_address_that_refuses_the_first_message_stays_unconfirmed(
    app: FastAPI, client: TestClient, session: Session, user: User
) -> None:
    app.dependency_overrides[delivery_sending] = Address(status=404).policy
    delivery_id = delivery(session, user, confirmed=False)

    response = client.post(f"/api/deliveries/{delivery_id}/confirm", headers=bearer(user))

    assert (response.status_code, response.json()["error"]) == (502, "delivery_failed")
    assert "answered 404" in response.json()["detail"]
    card = client.get(f"/api/deliveries/{delivery_id}", headers=bearer(user)).json()
    assert card["confirmed"] is False


def test_a_new_address_waits_for_its_own_confirmation(session: Session, user: User) -> None:
    delivery_id = delivery(session, user)
    access = DeliveryAccess(session, user, BOX)
    pipeline_id = service.view(access, delivery_id).pipeline_id

    changed = service.set_address(access, pipeline_id, "https://example.com/in")

    assert (changed.id, changed.confirmed, changed.service) == (delivery_id, False, "Webhook")


def test_cancelling_removes_it_and_another_persons_is_out_of_reach(
    app: FastAPI, client: TestClient, session: Session, user: User
) -> None:
    stranger = users.create(session, "stranger", hash_password("password-123", 1))
    theirs = delivery(session, stranger, confirmed=False)
    mine = delivery(session, user, confirmed=False)

    assert client.get(f"/api/deliveries/{theirs}", headers=bearer(user)).status_code == 404
    assert client.post(f"/api/deliveries/{theirs}/confirm", headers=bearer(user)).status_code == 404
    with pytest.raises(ToolException, match="not found"):
        tools(app, user)["set_delivery"].invoke({"delivery_id": theirs, "on": False})
    assert client.delete(f"/api/deliveries/{mine}", headers=bearer(user)).status_code == 204
    assert client.get(f"/api/deliveries/{mine}", headers=bearer(user)).status_code == 404


# --- sent when a run ends -------------------------------------------------------


def test_a_finished_run_posts_its_result_to_the_confirmed_address(
    app: FastAPI, session: Session, user: User
) -> None:
    delivery_id = delivery(session, user)
    address = Address()

    run = run_with(app, session, address)

    assert run.status == RunStatus.SUCCEEDED
    ((url, body),) = address.posted
    assert url == SLACK and body["text"].startswith("Digest finished\n\n")
    assert "Buzz" in body["text"]
    sent = tools(app, user)["list_deliveries"].invoke({})
    assert sent[0]["id"] == delivery_id
    assert sent[0]["last_sent_at"] is not None and sent[0]["last_error"] is None


def test_a_failed_run_says_why(app: FastAPI, session: Session, user: User) -> None:
    delivery(session, user, url="https://example.com/in")
    address = Address()
    broken = FailingProvider(llm_exceptions.ProviderTimeout("Model timed out"))

    run = run_with(app, session, address, agent=broken)

    assert run.status == RunStatus.FAILED
    ((_, body),) = address.posted
    assert (body["status"], body["run_id"]) == ("failed", run.id)
    assert body["result"] == run.error_detail != ""


def test_nothing_is_sent_while_unconfirmed_or_off(
    app: FastAPI, session: Session, user: User
) -> None:
    delivery_id = delivery(session, user, confirmed=False)
    address = Address()
    run_with(app, session, address)
    assert address.posted == []

    access = DeliveryAccess(session, user, BOX)
    asyncio.run(service.confirm(access, delivery_id, Address().policy()))
    tools(app, user)["set_delivery"].invoke({"delivery_id": delivery_id, "on": False})
    run_with(app, session, address)
    assert address.posted == []


def test_an_address_that_fails_never_changes_the_run(
    app: FastAPI, session: Session, user: User
) -> None:
    delivery(session, user)

    run = run_with(app, session, Address(status=500))

    assert run.status == RunStatus.SUCCEEDED
    assert "answered 500" in tools(app, user)["list_deliveries"].invoke({})[0]["last_error"]


def test_deleting_the_workflow_deletes_its_delivery(session: Session, user: User) -> None:
    delivery_id = delivery(session, user, confirmed=False)

    pipelines.delete(session, session.query(Pipeline).one())

    session.expire_all()
    assert session.get(Delivery, delivery_id) is None


def test_an_address_sealed_under_another_key_is_reported_not_raised(
    app: FastAPI, session: Session, user: User
) -> None:
    delivery_id = delivery(session, user)
    stored = session.get(Delivery, delivery_id)
    assert stored is not None
    stored.url_encrypted = secret_box_for(
        TEST_SETTINGS.model_copy(update={"secret_key": "another-key-" * 4})
    ).seal(SLACK)
    session.commit()

    run = run_with(app, session, Address())

    assert run.status == RunStatus.SUCCEEDED
    assert (
        "can no longer be read" in tools(app, user)["list_deliveries"].invoke({})[0]["last_error"]
    )
