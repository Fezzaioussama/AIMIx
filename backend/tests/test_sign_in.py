"""Sign-in hardening: the per-account failure limit, unknown usernames costing a
real password check, hash upgrades, and sign-out revoking access tokens."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import api.security
from api.deps import app_settings, token_signer
from api.exceptions import NotAuthenticated
from api.models import User
from api.repositories import users
from api.security import hash_iterations, verify_password
from api.services import accounts
from tests.conftest import TEST_SETTINGS
from tests.test_security import DJANGO_HASH, DJANGO_PASSWORD


def limit_failures(app: FastAPI, limit: int, **more: object) -> None:
    """At most ``limit`` failed sign-ins per username; no per-client limit in the way."""
    update = {"auth_account_failure_limit": limit, "auth_rate_limit_requests": 1_000, **more}
    chosen = TEST_SETTINGS.model_copy(update=update)
    app.dependency_overrides[app_settings] = lambda: chosen


def login(client: TestClient, username: str, password: str) -> int:
    return client.post("/api/login", json={"username": username, "password": password}).status_code


def test_an_account_is_locked_after_too_many_failed_sign_ins_from_any_client(
    app: FastAPI, client: TestClient, user: User, password: str
) -> None:
    limit_failures(app, 2)

    assert login(client, user.username, "wrong-1") == 401
    assert login(client, "TESTER", "wrong-2") == 401  # one counter, whatever the case
    locked = client.post("/api/login", json={"username": user.username, "password": password})

    # Refused before the password is checked, even the right one.
    assert locked.status_code == 429
    assert locked.json() == {"error": "throttled", "detail": accounts.ACCOUNT_THROTTLED}
    assert (
        0 < int(locked.headers["retry-after"]) <= TEST_SETTINGS.auth_account_failure_window_seconds
    )


def test_other_accounts_are_not_locked_with_it(
    app: FastAPI, client: TestClient, user: User, session: Session
) -> None:
    limit_failures(app, 1)
    users.create(session, "neighbour", api.security.hash_password("neighbour-pass-1", 1))

    assert login(client, user.username, "wrong") == 401
    assert login(client, user.username, "wrong") == 429
    assert login(client, "neighbour", "neighbour-pass-1") == 200


def test_unknown_usernames_are_locked_like_known_ones(app: FastAPI, client: TestClient) -> None:
    limit_failures(app, 1)

    assert login(client, "nobody", "wrong") == 401
    assert login(client, "nobody", "wrong") == 429


def test_a_successful_sign_in_clears_the_failures(
    app: FastAPI, client: TestClient, user: User, password: str
) -> None:
    limit_failures(app, 2)

    assert login(client, user.username, "wrong") == 401
    assert login(client, user.username, password) == 200
    assert login(client, user.username, "wrong") == 401
    assert login(client, user.username, "wrong") == 401
    assert login(client, user.username, password) == 429


def test_an_unknown_username_costs_a_full_password_check(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Answering faster for a username that does not exist would tell which do."""
    rounds: list[int] = []
    real = api.security._pbkdf2

    def counted(password: str, salt: str, iterations: int) -> str:
        rounds.append(iterations)
        return real(password, salt, iterations)

    monkeypatch.setattr(api.security, "_pbkdf2", counted)
    policy = accounts.SignInPolicy(7, 10, 900, TEST_SETTINGS.secret_key)
    credentials = accounts.Credentials("nobody", "a-guess")

    with pytest.raises(NotAuthenticated):
        accounts.sign_in(session, token_signer(TEST_SETTINGS), credentials, policy)

    assert rounds and set(rounds) == {7}


def test_signing_in_moves_an_imported_hash_to_the_configured_work_factor(
    app: FastAPI, client: TestClient, session: Session
) -> None:
    limit_failures(app, 10, password_hash_iterations=3)
    imported = users.create(session, "legacy", DJANGO_HASH)  # 1,000 iterations

    assert login(client, "legacy", DJANGO_PASSWORD) == 200

    session.refresh(imported)
    assert hash_iterations(imported.password_hash) == 3
    assert verify_password(DJANGO_PASSWORD, imported.password_hash)
    assert login(client, "legacy", DJANGO_PASSWORD) == 200


def test_a_failed_sign_in_leaves_the_hash_alone(
    app: FastAPI, client: TestClient, session: Session
) -> None:
    limit_failures(app, 10, password_hash_iterations=3)
    imported = users.create(session, "legacy", DJANGO_HASH)

    assert login(client, "legacy", "wrong") == 401

    session.refresh(imported)
    assert imported.password_hash == DJANGO_HASH


def test_signing_out_revokes_the_access_tokens_already_issued(
    client: TestClient, user: User, password: str
) -> None:
    access = client.post(
        "/api/login", json={"username": user.username, "password": password}
    ).json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    assert client.get("/api/protected", headers=headers).status_code == 200

    assert client.post("/api/token/logout").status_code == 204

    refused = client.get("/api/protected", headers=headers)
    assert refused.status_code == 401
    assert refused.json()["error"] == "not_authenticated"
    # Signing in again issues a token that works.
    fresh = client.post("/api/login", json={"username": user.username, "password": password})
    renewed = {"Authorization": f"Bearer {fresh.json()['access']}"}
    assert client.get("/api/protected", headers=renewed).status_code == 200


def test_a_token_of_another_version_is_refused(client: TestClient, user: User) -> None:
    stale = token_signer(TEST_SETTINGS).issue(user.id, "access", version=user.token_version + 1)
    response = client.get("/api/protected", headers={"Authorization": f"Bearer {stale}"})
    assert response.status_code == 401


def test_signing_out_with_a_rotated_refresh_token_changes_nothing(
    app: FastAPI, client: TestClient, user: User, password: str, session: Session
) -> None:
    client.post("/api/login", json={"username": user.username, "password": password})
    previous = client.cookies["aimix_refresh"]
    client.post("/api/token/refresh")
    version = user.token_version

    with TestClient(app) as replay_client:
        replay_client.cookies.set("aimix_refresh", previous, path="/api/token")
        assert replay_client.post("/api/token/logout").status_code == 204

    session.refresh(user)
    assert user.token_version == version
