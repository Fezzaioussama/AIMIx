"""Settings → Integrations over HTTP: each user's own MCP servers.

DNS is faked (``host_resolver``), so nothing here reaches the network.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.deps import host_resolver
from api.models import Integration, User
from api.repositories import users
from api.security import SecretBox, hash_password
from config.settings import HttpMCPServer, pin_settings
from tests.conftest import TEST_SETTINGS, bearer
from tests.mcp_fakes import DnsAnswer, resolver

URL = "/api/integrations"
SERVER = "https://crm.example/mcp"
TOKEN = "Bearer crm-secret-token-1234"


@pytest.fixture(autouse=True)
def dns(app: FastAPI) -> dict[str, DnsAnswer]:
    """Every host is public unless a test maps it to other addresses."""
    table: dict[str, DnsAnswer] = {}
    app.dependency_overrides[host_resolver] = lambda: resolver(table)
    return table


@pytest.fixture
def pinned() -> Iterator[None]:
    """Lets a test pin other settings; the test settings come back afterwards."""
    yield
    pin_settings(TEST_SETTINGS)


def body(**fields: Any) -> dict[str, Any]:
    return {
        "name": "crm",
        "url": SERVER,
        "headers": [{"name": "Authorization", "value": TOKEN}],
        **fields,
    }


def create(client: TestClient, **fields: Any) -> Response:
    return client.post(URL, json=body(**fields))


def stored_headers(session: Session, integration_id: int) -> dict[str, str]:
    row = session.get(Integration, integration_id)
    assert row is not None
    session.refresh(row)
    if not row.headers_encrypted:
        return {}
    values: dict[str, str] = json.loads(
        SecretBox(TEST_SETTINGS.secret_key).open(row.headers_encrypted)
    )
    return values


def test_a_new_integration_never_returns_header_values(auth_client: TestClient) -> None:
    response = create(auth_client)

    assert response.status_code == 201
    created = response.json()
    assert (created["name"], created["url"], created["enabled"]) == ("crm", SERVER, True)
    assert created["headers"] == [{"name": "Authorization", "hint": "1234"}]
    assert "crm-secret" not in response.text
    assert auth_client.get(URL).json() == [created]


def test_header_values_are_encrypted_at_rest(auth_client: TestClient, session: Session) -> None:
    created = create(auth_client).json()

    rows = session.execute(text("SELECT * FROM integrations")).all()
    assert "crm-secret" not in repr(rows)
    assert stored_headers(session, created["id"]) == {"Authorization": TOKEN}


def test_a_short_header_value_gets_no_hint(auth_client: TestClient) -> None:
    response = create(auth_client, headers=[{"name": "X-Team", "value": "ops"}])
    assert response.json()["headers"] == [{"name": "X-Team", "hint": ""}]


def test_integrations_are_private_to_each_user(
    client: TestClient, session: Session, user: User
) -> None:
    mine = client.post(URL, json=body(), headers=bearer(user)).json()
    other = bearer(users.create(session, "someone-else", hash_password("other-pass-123", 1)))

    assert client.get(URL, headers=other).json() == []
    for method, path in [
        ("PATCH", f"{URL}/{mine['id']}"),
        ("DELETE", f"{URL}/{mine['id']}"),
        ("POST", f"{URL}/{mine['id']}/test"),
    ]:
        response = client.request(method, path, json={"enabled": False}, headers=other)
        assert response.status_code == 404
        assert response.json()["error"] == "not_found"
    # The other user can use the same name for their own server.
    assert client.post(URL, json=body(), headers=other).status_code == 201


def test_an_update_keeps_the_headers_unless_it_sends_them(
    auth_client: TestClient, session: Session
) -> None:
    created = create(auth_client).json()
    path = f"{URL}/{created['id']}"

    first = auth_client.patch(path, json={"enabled": False, "name": "sales"})
    second = auth_client.patch(path, json={"enabled": False, "name": "sales"})

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert (first.json()["name"], first.json()["enabled"]) == ("sales", False)
    assert first.json()["headers"] == created["headers"]
    assert stored_headers(session, created["id"]) == {"Authorization": TOKEN}


def test_a_header_sent_without_a_value_keeps_its_saved_value(
    auth_client: TestClient, session: Session
) -> None:
    created = create(auth_client).json()
    headers = [{"name": "authorization"}, {"name": "X-Team", "value": "ops-team-0042"}]

    response = auth_client.patch(f"{URL}/{created['id']}", json={"headers": headers})

    assert response.status_code == 200
    assert response.json()["headers"] == [
        {"name": "authorization", "hint": "1234"},
        {"name": "X-Team", "hint": "0042"},
    ]
    assert stored_headers(session, created["id"]) == {
        "authorization": TOKEN,
        "X-Team": "ops-team-0042",
    }
    cleared = auth_client.patch(f"{URL}/{created['id']}", json={"headers": []})
    assert cleared.json()["headers"] == []
    assert stored_headers(session, created["id"]) == {}


def test_a_new_header_needs_a_value(auth_client: TestClient) -> None:
    created = create(auth_client).json()
    response = auth_client.patch(f"{URL}/{created['id']}", json={"headers": [{"name": "X-New"}]})
    assert response.status_code == 400
    assert response.json()["detail"] == "Enter a value for the X-New header."


def test_saved_values_never_follow_the_server_to_another_address(
    auth_client: TestClient, session: Session
) -> None:
    created = create(auth_client).json()
    path = f"{URL}/{created['id']}"
    moved = "https://elsewhere.example/mcp"

    for change in [{"url": moved}, {"url": moved, "headers": [{"name": "Authorization"}]}]:
        refused = auth_client.patch(path, json=change)
        assert refused.status_code == 400
        assert "enter every header value again" in refused.json()["detail"]

    same_server = auth_client.patch(path, json={"url": "https://crm.example/v2/mcp"})
    assert same_server.status_code == 200
    headers = [{"name": "Authorization", "value": "Bearer new-server-token-9999"}]
    accepted = auth_client.patch(path, json={"url": moved, "headers": headers})
    assert accepted.status_code == 200
    assert stored_headers(session, created["id"]) == {"Authorization": headers[0]["value"]}


def test_deleting_an_integration(auth_client: TestClient) -> None:
    created = create(auth_client).json()

    assert auth_client.delete(f"{URL}/{created['id']}").status_code == 204
    assert auth_client.delete(f"{URL}/{created['id']}").status_code == 404
    assert auth_client.get(URL).json() == []


@pytest.mark.parametrize(
    "fields",
    [
        {"name": "CRM"},
        {"name": "c"},
        {"name": "1crm"},
        {"name": "crm-tools"},
        {"name": "c" * 32},
        {"url": "not a url"},
        {"url": "ftp://crm.example/mcp"},
        {"url": "https://admin:secret@crm.example/mcp"},
        {"headers": [{"name": "Authorization"}]},
        {"headers": [{"name": "X-Key", "value": "a"}, {"name": "x-key", "value": "b"}]},
        {"headers": [{"name": "Host", "value": "internal"}]},
        {"headers": [{"name": "Bad Name", "value": "v"}]},
        {"headers": [{"name": "X-Key", "value": "v\r\nX-Injected: 1"}]},
        {"headers": [{"name": f"X-{index}", "value": "v"} for index in range(11)]},
    ],
)
def test_invalid_integrations_are_refused(auth_client: TestClient, fields: dict[str, Any]) -> None:
    response = create(auth_client, **fields)
    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"


def test_names_are_unique_per_user_and_never_a_built_in_servers(
    auth_client: TestClient, pinned: None
) -> None:
    assert create(auth_client).status_code == 201
    taken = create(auth_client)
    assert taken.json()["detail"] == "You already have an integration named crm."

    built_in = HttpMCPServer(transport="streamable_http", url="https://docs.example/mcp")
    pin_settings(TEST_SETTINGS.model_copy(update={"mcp_servers": {"docs": built_in}}))
    reserved = create(auth_client, name="docs")
    assert reserved.status_code == 400
    assert "built-in server" in reserved.json()["detail"]


def test_each_user_has_a_limited_number_of_integrations(auth_client: TestClient) -> None:
    for name in ("one", "two", "three"):
        assert create(auth_client, name=name).status_code == 201
    response = create(auth_client, name="four")
    assert response.status_code == 400
    assert "up to 3 integrations" in response.json()["detail"]


@pytest.mark.parametrize(
    "addresses",
    [
        ["127.0.0.1"],
        ["10.0.0.5"],
        ["172.16.4.2"],
        ["192.168.1.10"],
        ["169.254.169.254"],
        ["100.64.0.1"],
        ["0.0.0.0"],
        ["::1"],
        ["::ffff:127.0.0.1"],
        ["fe80::1%2"],
        ["fd00:ec2::254"],
        ["64:ff9b::a9fe:a9fe"],
        ["fec0::1"],
        ["::7f00:1"],
        ["ff02::1"],
        ["93.184.215.14", "10.0.0.5"],
    ],
)
def test_servers_on_non_public_addresses_are_refused(
    auth_client: TestClient, dns: dict[str, DnsAnswer], addresses: list[str]
) -> None:
    dns["internal.example"] = addresses
    response = create(auth_client, url="https://internal.example/mcp")
    assert response.status_code == 400
    assert "internal.example is not a public address" in response.json()["detail"]


@pytest.mark.parametrize("url", ["https://127.0.0.1/mcp", "https://[::1]:8443/mcp"])
def test_address_literals_are_checked_too(auth_client: TestClient, url: str) -> None:
    response = create(auth_client, url=url)
    assert response.status_code == 400
    assert "is not a public address" in response.json()["detail"]


def test_an_unknown_host_is_refused(auth_client: TestClient, dns: dict[str, DnsAnswer]) -> None:
    dns["nowhere.example"] = OSError("no such host")
    response = create(auth_client, url="https://nowhere.example/mcp")
    assert response.status_code == 400
    assert response.json()["detail"].startswith("Could not resolve nowhere.example.")


def test_a_host_name_no_resolver_accepts_is_refused_not_a_crash(
    auth_client: TestClient, dns: dict[str, DnsAnswer]
) -> None:
    host = "a" * 64 + ".example"  # one label over 63 characters fails IDNA encoding
    dns[host] = UnicodeError("encoding with 'idna' codec failed")
    response = create(auth_client, url=f"https://{host}/mcp")
    assert response.status_code == 400
    assert response.json()["detail"].startswith(f"Could not resolve {host}.")


def test_plain_http_is_refused_outside_local_development(auth_client: TestClient) -> None:
    response = create(auth_client, url="http://crm.example/mcp")
    assert response.status_code == 400
    assert response.json()["detail"] == "Enter the full server URL, starting with https."


def test_local_development_may_use_http_and_opt_in_to_private_servers(
    auth_client: TestClient, pinned: None
) -> None:
    pin_settings(TEST_SETTINGS.model_copy(update={"app_env": "local"}))
    assert create(auth_client, url="http://crm.example/mcp").status_code == 201
    loopback = create(auth_client, name="local", url="http://127.0.0.1:9787/mcp")
    assert loopback.status_code == 400

    allowed = {"app_env": "local", "integrations_allow_private_network": True}
    pin_settings(TEST_SETTINGS.model_copy(update=allowed))
    assert create(auth_client, name="local", url="http://127.0.0.1:9787/mcp").status_code == 201
