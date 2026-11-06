"""A forgotten password is reset by a link emailed to the account's address: asking
says nothing about who has an account, the link works once, and the address signs
in too."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.account_deps import mail_sender
from api.deps import app_settings
from api.models import User
from api.repositories import users
from api.services.email import Email
from tests.conftest import TEST_SETTINGS, bearer
from tests.email_fakes import Outbox, Refusing

ADDRESS = "alice@example.com"
NEW_PASSWORD = "a-brand-new-pass-4471"
LINK_START = "https://app.test/reset-password?"


@pytest.fixture
def outbox(app: FastAPI) -> Outbox:
    box = Outbox()
    app.dependency_overrides[mail_sender] = lambda: box
    return box


@pytest.fixture
def addressed(session: Session, user: User) -> User:
    users.set_email(session, user, ADDRESS)
    return user


def ask(client: TestClient, email: str) -> int:
    return client.post("/api/password-reset", json={"email": email}).status_code


def token_of(email: Email) -> str:
    link = next(line for line in email.text.splitlines() if line.startswith(LINK_START))
    return parse_qs(urlsplit(link).query)["token"][0]


def confirm(client: TestClient, token: str, password: str = NEW_PASSWORD) -> tuple[int, str]:
    body = {"token": token, "password": password}
    response = client.post("/api/password-reset/confirm", json=body)
    return response.status_code, response.json().get("detail", "") if response.content else ""


def login(client: TestClient, username: str, password: str) -> int:
    return client.post("/api/login", json={"username": username, "password": password}).status_code


def test_asking_emails_a_link_to_the_account_with_that_address(
    client: TestClient, outbox: Outbox, addressed: User
) -> None:
    assert ask(client, "Alice@Example.com") == 204

    (email,) = outbox.sent
    assert (email.to, email.subject) == (ADDRESS, "Reset your AIMIx password")
    assert addressed.username in email.text
    assert "within 30 minutes" in email.text
    assert token_of(email)


def test_asking_for_an_unknown_address_answers_the_same_and_sends_nothing(
    client: TestClient, outbox: Outbox, addressed: User
) -> None:
    assert ask(client, "nobody@example.com") == 204
    assert outbox.sent == []


def test_the_link_sets_a_new_password_once_and_ends_every_session(
    client: TestClient, outbox: Outbox, addressed: User, password: str
) -> None:
    before = bearer(addressed)
    ask(client, ADDRESS)
    token = token_of(outbox.sent[0])

    assert confirm(client, token) == (204, "")

    assert client.get("/api/protected", headers=before).status_code == 401
    assert login(client, addressed.username, NEW_PASSWORD) == 200
    assert login(client, addressed.username, password) == 401
    assert confirm(client, token, "yet-another-pass-9921") == (
        400,
        "token: This link is not valid any more. Ask for a new one.",
    )


def test_a_bad_token_or_a_weak_password_changes_nothing(
    client: TestClient, outbox: Outbox, addressed: User, password: str
) -> None:
    assert confirm(client, "not-a-token")[0] == 400
    ask(client, ADDRESS)
    token = token_of(outbox.sent[0])

    status, detail = confirm(client, token, "short")

    assert status == 400
    assert detail.startswith("password: This password is too short.")
    assert login(client, addressed.username, password) == 200
    assert confirm(client, token) == (204, "")  # the link still works


def test_an_access_token_is_not_a_reset_token(client: TestClient, addressed: User) -> None:
    access = bearer(addressed)["Authorization"].removeprefix("Bearer ")
    assert confirm(client, access)[0] == 400


def test_each_address_may_ask_a_few_times_per_window(
    app: FastAPI, client: TestClient, outbox: Outbox, addressed: User
) -> None:
    update = {"password_reset_rate_limit_requests": 2, "auth_rate_limit_requests": 1_000}
    app.dependency_overrides[app_settings] = lambda: TEST_SETTINGS.model_copy(update=update)

    assert [ask(client, ADDRESS) for _ in range(3)] == [204, 204, 429]

    assert len(outbox.sent) == 2
    assert ask(client, "other@example.com") == 204  # its own allowance


def test_without_a_mail_server_asking_is_refused_with_the_reason(
    client: TestClient, addressed: User
) -> None:
    # The test settings have no SMTP_HOST: the app's own sender refuses.
    response = client.post("/api/password-reset", json={"email": ADDRESS})

    assert response.status_code == 503
    assert response.json()["error"] == "email_not_configured"


def test_a_mail_server_that_refuses_is_a_502(
    app: FastAPI, client: TestClient, addressed: User
) -> None:
    app.dependency_overrides[mail_sender] = lambda: Refusing()

    response = client.post("/api/password-reset", json={"email": ADDRESS})

    assert (response.status_code, response.json()["error"]) == (502, "email_not_sent")


def test_signing_in_works_with_the_address_too(
    client: TestClient, addressed: User, password: str
) -> None:
    assert login(client, "Alice@example.com", password) == 200
    assert login(client, ADDRESS, "wrong") == 401


def test_registering_with_an_address_keeps_it_lower_cased_and_unique(
    client: TestClient, session: Session
) -> None:
    body = {"username": "bob", "password": "bob-strong-pass-123", "email": "Bob@Example.com"}

    assert client.post("/api/register", json=body).status_code == 201

    bob = users.get_by_username(session, "bob")
    assert bob is not None
    assert (bob.email, bob.email_notifications) == ("bob@example.com", True)
    taken = client.post("/api/register", json={**body, "username": "bob2"})
    assert taken.status_code == 400
    assert taken.json()["detail"] == "email: Another account uses this address."


@pytest.mark.parametrize("address", ["no-at-sign", "two@@x.com", "a b@x.com", "nodot@x"])
def test_an_address_that_cannot_be_one_is_refused(client: TestClient, address: str) -> None:
    assert client.post("/api/password-reset", json={"email": address}).status_code == 400
