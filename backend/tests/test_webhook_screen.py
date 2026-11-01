"""Settings → Webhooks over HTTP: a person lists their webhooks and result deliveries,
switches them, renews a webhook's link and deletes either, and another person's stay out
of reach. Confirming a delivery, which posts to its address, is rate limited."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.deps import app_settings
from api.models import Pipeline, User
from api.repositories import pipelines, users
from api.repositories.pipelines import PipelineChanges
from api.security import hash_password, secret_box_for
from api.services.catalog import default_model_id
from api.services.deliveries import service as deliveries
from api.services.deliveries.sender import SendPolicy
from api.services.deliveries.service import DeliveryAccess
from api.services.webhooks import service as webhooks
from api.services.webhooks.service import WebhookAccess
from api.webhook_deps import delivery_sending
from tests.conftest import TEST_SETTINGS, bearer

BOX = secret_box_for(TEST_SETTINGS)
SLACK = "https://hooks.slack.com/services/T000/B000/XyZ9"


def workflow(session: Session, owner: User, name: str = "Digest") -> Pipeline:
    step = {"order": 1, "stage": 1, "prompt": "Write about {input}", "model": default_model_id()}
    return pipelines.create_with_steps(session, owner, PipelineChanges(name, [], [step]))


def webhook(session: Session, owner: User, name: str = "Digest") -> int:
    pipeline = workflow(session, owner, name)
    return webhooks.link_for(WebhookAccess(session, owner, BOX), pipeline.id).id


def delivery(session: Session, owner: User) -> int:
    pipeline = workflow(session, owner)
    return deliveries.set_address(DeliveryAccess(session, owner, BOX), pipeline.id, SLACK).id


def token_of(client: TestClient, owner: User, webhook_id: int) -> str:
    token: str = client.get(f"/api/webhooks/{webhook_id}", headers=bearer(owner)).json()["token"]
    return token


def accepting() -> SendPolicy:
    """Sending that every address accepts, so confirming works offline."""
    return SendPolicy(
        5, 20_000, transport=lambda: httpx.MockTransport(lambda _: httpx.Response(200))
    )


def test_the_screen_lists_each_webhook_without_its_link(
    client: TestClient, session: Session, user: User
) -> None:
    first, second = webhook(session, user, "Digest"), webhook(session, user, "Report")

    listed = client.get("/api/webhooks", headers=bearer(user))

    assert listed.status_code == 200
    assert [(item["id"], item["pipeline_name"], item["enabled"]) for item in listed.json()] == [
        (first, "Digest", True),
        (second, "Report", True),
    ]
    assert all("token" not in item for item in listed.json())


def test_a_webhook_is_switched_off_and_on_again(
    client: TestClient, session: Session, user: User
) -> None:
    made = webhook(session, user)

    off = client.patch(f"/api/webhooks/{made}", json={"enabled": False}, headers=bearer(user))
    on = client.patch(f"/api/webhooks/{made}", json={"enabled": True}, headers=bearer(user))

    assert (off.status_code, off.json()["enabled"]) == (200, False)
    assert (on.status_code, on.json()["enabled"]) == (200, True)


def test_renewing_gives_a_new_link_and_the_old_one_stops_working(
    client: TestClient, session: Session, user: User
) -> None:
    made = webhook(session, user)
    before = token_of(client, user, made)

    renewed = client.post(f"/api/webhooks/{made}/renew", headers=bearer(user))

    assert renewed.status_code == 200
    assert "token" not in renewed.json()
    assert token_of(client, user, made) != before
    assert client.post(f"/api/hooks/{before}", json={}).status_code == 404


def test_deleting_a_webhook_ends_its_link(client: TestClient, session: Session, user: User) -> None:
    made = webhook(session, user)
    token = token_of(client, user, made)

    assert client.delete(f"/api/webhooks/{made}", headers=bearer(user)).status_code == 204
    assert client.get(f"/api/webhooks/{made}", headers=bearer(user)).status_code == 404
    assert client.post(f"/api/hooks/{token}", json={}).status_code == 404
    assert client.get("/api/webhooks", headers=bearer(user)).json() == []


def test_the_screen_lists_and_switches_result_deliveries_without_their_address(
    client: TestClient, session: Session, user: User
) -> None:
    made = delivery(session, user)

    listed = client.get("/api/deliveries", headers=bearer(user)).json()
    off = client.patch(f"/api/deliveries/{made}", json={"enabled": False}, headers=bearer(user))

    assert [
        (item["id"], item["service"], item["destination"], item["confirmed"]) for item in listed
    ] == [(made, "Slack", "hooks.slack.com", False)]
    assert SLACK not in json.dumps(listed)
    assert (off.status_code, off.json()["enabled"]) == (200, False)


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("PATCH", "/api/webhooks/{hook}", {"enabled": False}),
        ("POST", "/api/webhooks/{hook}/renew", None),
        ("DELETE", "/api/webhooks/{hook}", None),
        ("PATCH", "/api/deliveries/{delivery}", {"enabled": False}),
        ("DELETE", "/api/deliveries/{delivery}", None),
    ],
)
def test_another_persons_webhooks_and_deliveries_are_out_of_reach(
    client: TestClient,
    session: Session,
    user: User,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    stranger = users.create(session, "stranger", hash_password("password-123", 1))
    url = path.format(hook=webhook(session, stranger), delivery=delivery(session, stranger))

    assert client.request(method, url, json=body, headers=bearer(user)).status_code == 404
    assert client.get("/api/webhooks", headers=bearer(user)).json() == []
    assert client.get("/api/deliveries", headers=bearer(user)).json() == []


@pytest.mark.parametrize("body", [{}, {"enabled": "maybe"}, {"enabled": None}])
def test_a_switch_takes_a_yes_or_no(
    client: TestClient, session: Session, user: User, body: dict[str, Any]
) -> None:
    made = webhook(session, user)

    response = client.patch(f"/api/webhooks/{made}", json=body, headers=bearer(user))

    assert (response.status_code, response.json()["error"]) == (400, "validation_error")


def test_confirming_a_delivery_is_rate_limited_per_account(
    app: FastAPI, client: TestClient, session: Session, user: User
) -> None:
    limited = TEST_SETTINGS.model_copy(update={"user_rate_limit_requests": 1})
    app.dependency_overrides[app_settings] = lambda: limited
    app.dependency_overrides[delivery_sending] = accepting
    made = delivery(session, user)

    first = client.post(f"/api/deliveries/{made}/confirm", headers=bearer(user))
    again = client.post(f"/api/deliveries/{made}/confirm", headers=bearer(user))

    assert (first.status_code, first.json()["confirmed"]) == (200, True)
    assert (again.status_code, again.json()["error"]) == (429, "throttled")
