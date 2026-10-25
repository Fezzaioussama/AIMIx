"""Each integration's "Ask me before its tools act" switch, over HTTP. DNS is
faked (``host_resolver``), so nothing here reaches the network."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from api.deps import host_resolver
from api.models import Integration, User
from api.repositories import users
from api.security import hash_password
from tests.conftest import bearer
from tests.mcp_fakes import DnsAnswer, resolver

URL = "/api/integrations"
SERVER = "https://crm.example/mcp"


@pytest.fixture(autouse=True)
def dns(app: FastAPI) -> dict[str, DnsAnswer]:
    """Every host is public, so the address check passes without a network."""
    table: dict[str, DnsAnswer] = {}
    app.dependency_overrides[host_resolver] = lambda: resolver(table)
    return table


def create(client: TestClient, **fields: Any) -> Response:
    return client.post(URL, json={"name": "crm", "url": SERVER, **fields})


def stored(session: Session, integration_id: int) -> Integration:
    row = session.get(Integration, integration_id)
    assert row is not None
    session.refresh(row)
    return row


def test_a_new_integration_asks_before_its_tools_act(
    auth_client: TestClient, session: Session
) -> None:
    created = create(auth_client).json()

    assert created["require_approval"] is True
    assert stored(session, created["id"]).require_approval is True
    assert auth_client.get(URL).json()[0]["require_approval"] is True


def test_an_integration_can_be_connected_as_trusted(auth_client: TestClient) -> None:
    created = create(auth_client, require_approval=False).json()

    assert created["require_approval"] is False


def test_the_switch_is_saved_and_safe_to_send_twice(
    auth_client: TestClient, session: Session
) -> None:
    integration_id = create(auth_client).json()["id"]
    path = f"{URL}/{integration_id}"

    first = auth_client.patch(path, json={"require_approval": False})
    again = auth_client.patch(path, json={"require_approval": False})
    back = auth_client.patch(path, json={"require_approval": True})

    assert [response.json()["require_approval"] for response in (first, again, back)] == [
        False,
        False,
        True,
    ]
    assert stored(session, integration_id).require_approval is True


def test_other_edits_leave_the_switch_alone_and_the_switch_leaves_them_alone(
    auth_client: TestClient,
) -> None:
    integration_id = create(auth_client, require_approval=False).json()["id"]
    path = f"{URL}/{integration_id}"

    paused = auth_client.patch(path, json={"enabled": False}).json()
    trusted = auth_client.patch(path, json={"require_approval": True}).json()

    assert (paused["enabled"], paused["require_approval"]) == (False, False)
    assert (trusted["enabled"], trusted["require_approval"]) == (False, True)
    assert trusted["name"] == "crm"


def test_the_switch_must_be_a_boolean(auth_client: TestClient) -> None:
    integration_id = create(auth_client).json()["id"]

    response = auth_client.patch(f"{URL}/{integration_id}", json={"require_approval": "maybe"})

    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"


def test_nobody_else_can_change_the_switch(
    auth_client: TestClient, client: TestClient, session: Session, user: User
) -> None:
    mine = create(auth_client).json()
    stranger = bearer(users.create(session, "someone-else", hash_password("other-pass-123", 1)))

    response = client.patch(
        f"{URL}/{mine['id']}", json={"require_approval": False}, headers=stranger
    )

    assert response.status_code == 404
    assert stored(session, mine["id"]).require_approval is True
