"""OAuth sign-in to a user's MCP server: started from Settings, finished by the
authorization server's call back, then every connection signs with the token and
renews it once it has expired. The authorization server is faked over HTTP; DNS too."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.integration_deps import host_resolver, oauth_sign_in
from api.models import Integration, User
from api.repositories import integrations as repository
from api.repositories import users
from api.security import SecretBox, hash_password
from api.services.integrations.bearer import OAuthBearer
from api.services.integrations.connections import mcp_connections_for
from api.services.integrations.oauth import (
    CALLBACK_PATH,
    NO_REGISTRATION,
    TOO_LATE,
    UNMATCHED,
    OAuthPolicy,
)
from api.services.integrations.oauth_tokens import CONNECTED, PENDING, Tokens, seal, tokens_of
from config.settings import get_settings
from tests.conftest import TEST_SETTINGS, bearer
from tests.mcp_fakes import resolver
from tests.test_integrations import SERVER, create

AUTH = "https://crm.example"
APP = "http://app.test"
BOX = SecretBox(TEST_SETTINGS.secret_key)


class AuthServer:
    """A fake authorization server at the MCP server's origin: its metadata, client
    registration and token endpoint, which records what it is asked."""

    def __init__(self, registration: bool = True) -> None:
        self.registration = registration
        self.token_requests: list[dict[str, str]] = []
        self.issued = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/.well-known/oauth-authorization-server":
            metadata: dict[str, Any] = {
                "issuer": AUTH,
                "authorization_endpoint": f"{AUTH}/authorize",
                "token_endpoint": f"{AUTH}/token",
                "code_challenge_methods_supported": ["S256"],
            }
            if self.registration:
                metadata["registration_endpoint"] = f"{AUTH}/register"
            return httpx.Response(200, json=metadata)
        if path == "/register":
            registered = {**json.loads(request.content), "client_id": "aimix-1"}
            return httpx.Response(201, json=registered)
        if path == "/token":
            form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
            self.token_requests.append(form)
            self.issued += 1
            token = {"access_token": f"at-{self.issued}", "token_type": "bearer"}
            return httpx.Response(200, json={**token, "expires_in": 3600, "refresh_token": "rt-1"})
        return httpx.Response(404)

    def policy(self, attempt_seconds: float = 600) -> OAuthPolicy:
        transport = lambda: httpx.MockTransport(self.handle)  # noqa: E731
        return OAuthPolicy(f"{APP}{CALLBACK_PATH}", APP, attempt_seconds, 5, transport)


@pytest.fixture(autouse=True)
def dns(app: FastAPI) -> None:
    """Every host is public, so the servers' addresses pass."""
    app.dependency_overrides[host_resolver] = lambda: resolver({})


@pytest.fixture
def auth_server(app: FastAPI) -> AuthServer:
    fake = AuthServer()
    app.dependency_overrides[oauth_sign_in] = fake.policy
    return fake


def integration_id(auth_client: TestClient) -> int:
    response = create(auth_client)
    assert response.status_code == 201, response.text
    made: int = response.json()["id"]
    return made


def start(auth_client: TestClient, integration: int) -> dict[str, str]:
    """The sign-in page's query, as the browser would carry it to the authorization server."""
    response = auth_client.post(f"/api/integrations/{integration}/oauth")
    assert response.status_code == 200, response.text
    url: str = response.json()["authorization_url"]
    assert url.startswith(f"{AUTH}/authorize?")
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


def come_back(client: TestClient, query: str) -> str:
    """Where the call back sends the browser."""
    response = client.get(f"{CALLBACK_PATH}?{query}", follow_redirects=False)
    assert response.status_code == 303, response.text
    location: str = response.headers["location"]
    return location


def status_of(auth_client: TestClient, integration: int) -> str:
    listed = {item["id"]: item for item in auth_client.get("/api/integrations").json()}
    oauth: str = listed[integration]["oauth"]
    return oauth


def row_of(session: Session, integration: int) -> Integration:
    row = session.get(Integration, integration)
    assert row is not None
    session.refresh(row)
    return row


def test_the_owner_signs_in_and_the_call_back_connects_the_integration(
    auth_client: TestClient, client: TestClient, session: Session, auth_server: AuthServer
) -> None:
    integration = integration_id(auth_client)

    query = start(auth_client, integration)

    assert (query["response_type"], query["client_id"]) == ("code", "aimix-1")
    assert (query["redirect_uri"], query["resource"]) == (f"{APP}{CALLBACK_PATH}", SERVER)
    assert query["code_challenge_method"] == "S256" and query["code_challenge"] and query["state"]
    assert status_of(auth_client, integration) == PENDING

    landed = come_back(client, f"code=abc&state={query['state']}")

    assert landed == f"{APP}/settings/integrations?connected=crm"
    (exchange,) = auth_server.token_requests
    assert (exchange["grant_type"], exchange["code"], exchange["client_id"]) == (
        "authorization_code",
        "abc",
        "aimix-1",
    )
    assert exchange["redirect_uri"] == f"{APP}{CALLBACK_PATH}" and exchange["resource"] == SERVER
    assert exchange["code_verifier"]
    assert status_of(auth_client, integration) == CONNECTED
    row = row_of(session, integration)
    assert row.oauth_state_hash is None and "at-1" not in row.oauth_encrypted
    assert tokens_of(BOX, row).access_token == "at-1"


def test_a_wrong_refused_or_late_call_back_lands_with_an_error(
    app: FastAPI, auth_client: TestClient, client: TestClient, auth_server: AuthServer
) -> None:
    integration = integration_id(auth_client)
    query = start(auth_client, integration)

    def error_of(landed: str) -> str:
        return parse_qs(urlsplit(landed).query)["oauth_error"][0]

    assert error_of(come_back(client, "code=abc&state=nope")) == UNMATCHED
    refused = error_of(come_back(client, f"error=access_denied&state={query['state']}"))
    assert refused == "The sign-in was refused (access_denied)."
    app.dependency_overrides[oauth_sign_in] = lambda: auth_server.policy(attempt_seconds=-1)
    late = start(auth_client, integration)
    assert error_of(come_back(client, f"code=abc&state={late['state']}")) == TOO_LATE
    assert status_of(auth_client, integration) == PENDING
    assert auth_server.token_requests == []


def test_connections_sign_with_the_token_and_renew_it_once_expired(
    app: FastAPI,
    auth_client: TestClient,
    client: TestClient,
    session: Session,
    user: User,
    auth_server: AuthServer,
) -> None:
    integration = integration_id(auth_client)
    come_back(client, f"code=abc&state={start(auth_client, integration)['state']}")

    def built() -> OAuthBearer:
        connections = mcp_connections_for(app.state.database, user, get_settings())
        auth = connections.user["crm"]["auth"]  # type: ignore[typeddict-item]
        assert isinstance(auth, OAuthBearer)
        return auth

    async def signed(auth: OAuthBearer) -> tuple[list[dict[str, str]], str]:
        """Drive the auth flow as httpx would, the fake server answering a renewal."""
        renewals: list[dict[str, str]] = []
        flow = auth.async_auth_flow(httpx.Request("GET", SERVER))
        request = await flow.__anext__()
        while request.url.path == "/token":
            renewals.append({k: v[0] for k, v in parse_qs(request.content.decode()).items()})
            response = auth_server.handle(request)
            response.request = request
            request = await flow.asend(response)
        return renewals, request.headers["Authorization"]

    assert asyncio.run(signed(built())) == ([], "Bearer at-1")

    fresh = tokens_of(BOX, row_of(session, integration))
    stale = Tokens("at-1", "rt-1", time.time() - 10, SERVER, fresh.client)
    repository.set_oauth(session, row_of(session, integration), CONNECTED, seal(BOX, stale), None)
    renewals, header = asyncio.run(signed(built()))

    assert header == "Bearer at-2"
    (renewal,) = renewals
    assert (renewal["grant_type"], renewal["refresh_token"], renewal["client_id"]) == (
        "refresh_token",
        "rt-1",
        "aimix-1",
    )
    # Kept, so the next connection starts with the renewed token.
    assert tokens_of(BOX, row_of(session, integration)).access_token == "at-2"


def test_a_server_without_client_registration_cannot_be_connected(
    app: FastAPI, auth_client: TestClient
) -> None:
    app.dependency_overrides[oauth_sign_in] = AuthServer(registration=False).policy
    integration = integration_id(auth_client)

    refused = auth_client.post(f"/api/integrations/{integration}/oauth")

    assert (refused.status_code, refused.json()["error"]) == (400, "validation_error")
    assert refused.json()["detail"] == NO_REGISTRATION
    assert status_of(auth_client, integration) == ""


def test_signing_out_forgets_the_tokens_and_others_integrations_are_out_of_reach(
    auth_client: TestClient, client: TestClient, session: Session, auth_server: AuthServer
) -> None:
    integration = integration_id(auth_client)
    come_back(client, f"code=abc&state={start(auth_client, integration)['state']}")

    out = auth_client.delete(f"/api/integrations/{integration}/oauth")

    assert (out.status_code, out.json()["oauth"]) == (200, "")
    assert row_of(session, integration).oauth_encrypted == ""
    stranger = users.create(session, "stranger", hash_password("x-pass-2891", 1))
    for method in ("POST", "DELETE"):
        path = f"/api/integrations/{integration}/oauth"
        assert auth_client.request(method, path, headers=bearer(stranger)).status_code == 404
