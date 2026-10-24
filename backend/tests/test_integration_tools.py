"""A user's integrations next to the operator's MCP servers: one connection
builder, discovery that survives a failing integration, and the tool catalogue.

MCP servers and DNS are faked (``tests/mcp_fakes.py``); nothing reaches the network.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_mcp_adapters.sessions import Connection
from sqlalchemy.orm import Session

from api.exceptions import ToolUnavailable
from api.models import User
from api.repositories import integrations as repository
from api.repositories import users
from api.repositories.integrations import IntegrationChanges
from api.security import SecretBox, hash_password
from api.services import mcp_discovery
from api.services.addresses import AddressNotAllowed
from api.services.integrations.connections import GuardedClientFactory, mcp_connections_for
from api.services.integrations.headers import seal
from api.services.mcp import MCPConnections
from config.settings import HttpMCPServer, get_settings, pin_settings
from tests.conftest import TEST_SETTINGS
from tests.mcp_fakes import FakeServers, ServerBehaviour, fake_tool, resolver

TOKEN = "Bearer crm-secret-token-1234"
DOCS = HttpMCPServer(transport="streamable_http", url="https://docs.example/mcp")


def save_integration(session: Session, owner: User, name: str, **fields: Any) -> int:
    box = SecretBox(fields.pop("secret_key", TEST_SETTINGS.secret_key))
    changes = IntegrationChanges(
        name=name,
        url=fields.pop("url", f"https://{name}.example/mcp"),
        enabled=fields.pop("enabled", True),
        headers=seal(box, fields.pop("headers", {"Authorization": TOKEN})),
    )
    return repository.create(session, owner, changes).id


@pytest.fixture
def operator_docs() -> Iterator[None]:
    """An operator server named ``docs`` in MCP_SERVERS."""
    pin_settings(TEST_SETTINGS.model_copy(update={"mcp_servers": {"docs": DOCS}}))
    yield
    pin_settings(TEST_SETTINGS)


def servers(monkeypatch: pytest.MonkeyPatch, behaviour: dict[str, ServerBehaviour]) -> FakeServers:
    fake = FakeServers(behaviour)
    monkeypatch.setattr(mcp_discovery, "MultiServerMCPClient", fake)
    return fake


@pytest.mark.usefixtures("operator_docs")
def test_one_builder_merges_operator_servers_and_enabled_integrations(
    app: FastAPI, session: Session, user: User
) -> None:
    stranger = users.create(session, "stranger", hash_password("password-123", 1))
    save_integration(session, user, "crm")
    save_integration(session, user, "paused", enabled=False)
    save_integration(session, stranger, "theirs")

    built = mcp_connections_for(app.state.database, user, get_settings())

    assert (set(built.operator), set(built.user)) == ({"docs"}, {"crm"})
    crm = cast(dict[str, Any], built.user["crm"])
    assert (crm["url"], crm["headers"]) == ("https://crm.example/mcp", {"Authorization": TOKEN})
    assert isinstance(crm["httpx_client_factory"], GuardedClientFactory)
    assert "httpx_client_factory" not in cast(dict[str, Any], built.operator["docs"])


@pytest.mark.usefixtures("operator_docs")
def test_an_integration_that_cannot_be_used_now_is_skipped(
    app: FastAPI, session: Session, user: User, caplog: pytest.LogCaptureFixture
) -> None:
    # Saved before the operator added "docs", and under another SECRET_KEY.
    save_integration(session, user, "docs")
    save_integration(session, user, "rotated", secret_key="an-older-secret-key")

    with caplog.at_level(logging.WARNING):
        built = mcp_connections_for(app.state.database, user, get_settings())

    assert built.user == {}
    assert "integration=docs reason=name_taken" in caplog.text
    assert "integration=rotated reason=UnreadableSecret" in caplog.text
    assert "crm-secret" not in caplog.text


def test_local_private_servers_use_the_default_client(
    app: FastAPI, session: Session, user: User
) -> None:
    allowed = {"app_env": "local", "integrations_allow_private_network": True}
    pin_settings(TEST_SETTINGS.model_copy(update=allowed))
    try:
        save_integration(session, user, "local", url="http://127.0.0.1:9787/mcp")
        built = mcp_connections_for(app.state.database, user, get_settings())
    finally:
        pin_settings(TEST_SETTINGS)
    assert "httpx_client_factory" not in cast(dict[str, Any], built.user["local"])


@pytest.mark.asyncio
async def test_every_request_to_an_integration_rechecks_its_address() -> None:
    guard = GuardedClientFactory(1, resolver({"crm.example": ["10.0.0.5"]}))

    with pytest.raises(AddressNotAllowed, match=r"crm\.example is not a public address"):
        await guard.check(httpx.Request("POST", "https://crm.example/mcp"))
    await guard.check(httpx.Request("POST", "https://public.example/mcp"))
    async with guard(headers={"Authorization": TOKEN}) as client:
        assert client.event_hooks["request"] == [guard.check]
        assert client.headers["authorization"] == TOKEN


def user_servers(*names: str) -> MCPConnections:
    return MCPConnections(user=cast(dict[str, Connection], {name: {} for name in names}))


@pytest.mark.asyncio
async def test_a_failing_integration_is_skipped_and_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    servers(monkeypatch, {"crm": httpx.ConnectError("down"), "sales": ["lookup"]})
    native = fake_tool("calculator")

    with caplog.at_level(logging.WARNING):
        tools = await mcp_discovery.discover_tools(user_servers("crm", "sales"), [native], 1)

    assert [item.name for item in tools] == ["calculator", "sales_lookup"]
    assert mcp_discovery.integration_of(tools[1]) == "sales"
    assert mcp_discovery.integration_of(native) is None
    assert "integration.discovery_skipped integration=crm error=ConnectError" in caplog.text


@pytest.mark.asyncio
async def test_a_failing_operator_server_still_stops_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    servers(monkeypatch, {"docs": httpx.ConnectError("down"), "crm": ["search"]})
    configured = MCPConnections(
        operator=cast(dict[str, Connection], {"docs": {}}),
        user=cast(dict[str, Connection], {"crm": {}}),
    )
    with pytest.raises(ToolUnavailable, match="An MCP server is unavailable"):
        await mcp_discovery.discover_tools(configured, [], 1)


@pytest.mark.asyncio
async def test_integration_tools_never_take_another_tools_name(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    servers(monkeypatch, {"crm": ["search", "bad.name", "ok"]})
    native = fake_tool("crm_search")

    with caplog.at_level(logging.WARNING):
        tools = await mcp_discovery.discover_tools(user_servers("crm"), [native], 1)

    assert [item.name for item in tools] == ["crm_search", "crm_ok"]
    assert mcp_discovery.integration_of(tools[0]) is None
    assert "integration.tools_dropped integration=crm count=2" in caplog.text


def test_the_catalogue_labels_integration_tools_with_their_name(
    auth_client: TestClient, session: Session, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_integration(session, user, "crm")
    servers(monkeypatch, {"crm": ["search_contacts"]})

    listed = {item["name"]: item for item in auth_client.get("/api/agent-tools").json()}

    assert listed["crm_search_contacts"] == {
        "name": "crm_search_contacts",
        "description": "Does a thing.",
        "source": "crm",
    }
    assert listed["calculator"]["source"] == "AIMIx"


def test_the_catalogue_survives_an_unreachable_integration(
    auth_client: TestClient, session: Session, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_integration(session, user, "crm")
    servers(monkeypatch, {"crm": httpx.ConnectError("down")})

    response = auth_client.get("/api/agent-tools")

    assert response.status_code == 200
    assert {item["source"] for item in response.json()} == {"AIMIx"}
