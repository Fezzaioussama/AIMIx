"""The chats a person keeps (``/api/chats``): listed the last written first, opened
with their messages, named, deleted, capped per account, and never another's."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.deps import app_settings
from api.exceptions import ValidationFailed
from api.models import CHAT_TITLE_MAX_LENGTH
from api.repositories import chats as repository
from api.repositories import users
from api.repositories.quota import Quota
from api.security import hash_password
from api.services.chats import title_of
from tests.conftest import TEST_SETTINGS

NO_USAGE = {"input_tokens": 0, "output_tokens": 0, "cost_usd": None, "cost_complete": True}


def create(client: TestClient, title: str = "") -> dict[str, Any]:
    response = client.post("/api/chats", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()


def test_chats_are_listed_the_last_written_first(auth_client: TestClient) -> None:
    first = create(auth_client)
    second = create(auth_client, "Named")

    listed = auth_client.get("/api/chats").json()

    assert [(chat["id"], chat["title"]) for chat in listed] == [
        (second["id"], "Named"),
        (first["id"], ""),
    ]
    assert "messages" not in listed[0]


def test_a_new_chat_opens_empty(auth_client: TestClient) -> None:
    chat = create(auth_client)

    detail = auth_client.get(f"/api/chats/{chat['id']}").json()

    assert detail["title"] == ""
    assert detail["messages"] == []
    assert detail["usage"] == NO_USAGE


def test_a_chat_is_renamed_and_deleted(auth_client: TestClient) -> None:
    chat = create(auth_client)

    renamed = auth_client.patch(f"/api/chats/{chat['id']}", json={"title": "  Digest plans "})
    blank = auth_client.patch(f"/api/chats/{chat['id']}", json={"title": "   "})
    deleted = auth_client.delete(f"/api/chats/{chat['id']}")

    assert (renamed.status_code, renamed.json()["title"]) == (200, "Digest plans")
    assert (blank.status_code, blank.json()["error"]) == (400, "validation_error")
    assert deleted.status_code == 204
    assert auth_client.get(f"/api/chats/{chat['id']}").status_code == 404
    assert auth_client.get("/api/chats").json() == []


def test_another_users_chat_is_not_found(auth_client: TestClient, session: Session) -> None:
    neighbour = users.create(session, "neighbour", hash_password("neighbour-pass-1234", 1))
    theirs = repository.create(session, neighbour, "Theirs", Quota(10, ValidationFailed("no")))

    assert auth_client.get(f"/api/chats/{theirs.id}").status_code == 404
    assert auth_client.patch(f"/api/chats/{theirs.id}", json={"title": "Mine"}).status_code == 404
    assert auth_client.delete(f"/api/chats/{theirs.id}").status_code == 404
    assert auth_client.get("/api/chats").json() == []
    session.refresh(theirs)
    assert theirs.title == "Theirs"


def test_an_account_keeps_at_most_chats_max_per_user(app: FastAPI, auth_client: TestClient) -> None:
    app.dependency_overrides[app_settings] = lambda: TEST_SETTINGS.model_copy(
        update={"chats_max_per_user": 2}
    )
    create(auth_client)
    create(auth_client)

    response = auth_client.post("/api/chats", json={})

    assert response.status_code == 400
    assert response.json()["detail"] == "You can keep up to 2 chats. Delete one first."
    assert len(auth_client.get("/api/chats").json()) == 2


def test_a_title_is_the_first_line_squeezed_and_cut() -> None:
    assert title_of("\n  Build   a digest \nfor my team") == "Build a digest"
    assert title_of("   ") == ""
    cut = title_of("word " * 40)
    assert len(cut) == CHAT_TITLE_MAX_LENGTH
    assert cut.endswith("word…")
