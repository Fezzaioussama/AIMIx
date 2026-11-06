"""The account's email address and notification switch: read, set with the password
asked again, removed, and part of the account's copy."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.models import User
from api.repositories import users
from api.security import hash_password

ADDRESS = "alice@example.com"


def account(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/account")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def set_email(client: TestClient, email: str | None, password: str) -> tuple[int, dict[str, Any]]:
    response = client.put("/api/account/email", json={"email": email, "password": password})
    return response.status_code, response.json()


def test_a_new_account_has_no_address_and_notifications_on(
    auth_client: TestClient, user: User
) -> None:
    assert account(auth_client) == {
        "username": user.username,
        "email": None,
        "email_notifications": True,
        "created_at": account(auth_client)["created_at"],
        "llm_provider": None,
    }


def test_the_address_is_set_with_the_password_and_kept_lower_cased(
    auth_client: TestClient, password: str
) -> None:
    status, body = set_email(auth_client, " Alice@Example.com ", password)

    assert (status, body["email"]) == (200, ADDRESS)
    assert account(auth_client)["email"] == ADDRESS


def test_a_wrong_password_or_a_taken_address_changes_nothing(
    auth_client: TestClient, session: Session, password: str
) -> None:
    neighbour = users.create(session, "neighbour", hash_password("neighbour-pass-1234", 1))
    users.set_email(session, neighbour, "taken@example.com")

    wrong = set_email(auth_client, ADDRESS, "not-the-password")
    taken = set_email(auth_client, "Taken@example.com", password)

    assert (wrong[0], wrong[1]["detail"]) == (400, "password: The password is not correct.")
    assert (taken[0], taken[1]["detail"]) == (400, "email: Another account uses this address.")
    assert account(auth_client)["email"] is None


def test_the_address_can_be_removed(auth_client: TestClient, password: str) -> None:
    set_email(auth_client, ADDRESS, password)

    status, body = set_email(auth_client, None, password)

    assert (status, body["email"]) == (200, None)


def test_notifications_can_be_switched_off_and_on(auth_client: TestClient) -> None:
    off = auth_client.put("/api/account/notifications", json={"email_notifications": False})
    assert (off.status_code, off.json()["email_notifications"]) == (200, False)
    assert account(auth_client)["email_notifications"] is False
    on = auth_client.put("/api/account/notifications", json={"email_notifications": True})
    assert on.json()["email_notifications"] is True


def test_the_copy_of_the_account_holds_the_address(auth_client: TestClient, password: str) -> None:
    set_email(auth_client, ADDRESS, password)

    exported = auth_client.get("/api/account/export").json()["account"]

    assert (exported["email"], exported["email_notifications"]) == (ADDRESS, True)
