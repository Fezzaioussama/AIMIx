"""A kept chat remembers (``POST /api/chat`` with a ``chat_id``): both sides of each
exchange are saved with the tools and usage of the reply, the assistant reads what
was said before, and once that outgrows CHAT_HISTORY_MAX_CHARS the oldest messages
become the assistant's own notes, read in their place from then on."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.deps import app_settings
from api.exceptions import ValidationFailed
from api.models import Chat
from api.repositories import chats as repository
from api.repositories import users
from api.repositories.quota import Quota
from api.security import hash_password
from api.services.chat_conversation import ChatTurn, Conversation
from api.services.chat_events import (
    ChatEvent,
    text_event,
    tool_finished,
    tool_started,
    usage_event,
)
from llm.usage import TokenUsage
from tests.conftest import TEST_SETTINGS, FakeAgent, use_agent

NDJSON = {"Accept": "application/x-ndjson"}
SCHEDULE = {
    "id": 7,
    "pipeline_name": "Digest",
    "frequency": "daily",
    "time": "09:00",
    "timezone": "Europe/Paris",
    "enabled": True,
}
NOTES_1 = "notes 1: 1 messages folded in"


class ToolAgent(FakeAgent):
    """Replies with a tool it used, then its text, then what it all used."""

    async def stream(self, conversation: Conversation) -> AsyncIterator[ChatEvent]:
        self.conversations.append(conversation)
        yield tool_started("create_schedule")
        yield tool_finished("create_schedule", SCHEDULE)
        yield text_event("Scheduled ")
        yield text_event("it.")
        yield usage_event(TokenUsage.of(120, 30, 0.002))


def new_chat(client: TestClient) -> int:
    chat_id: int = client.post("/api/chats", json={}).json()["id"]
    return chat_id


def say(client: TestClient, chat_id: int, prompt: str, **extra: Any) -> list[dict[str, Any]]:
    body = {"prompt": prompt, "chat_id": chat_id, **extra}
    response = client.post("/api/chat", json=body, headers=NDJSON)
    assert response.status_code == 200, response.text
    return [json.loads(line) for line in response.text.splitlines() if line]


def limits(app: FastAPI, **update: int) -> None:
    app.dependency_overrides[app_settings] = lambda: TEST_SETTINGS.model_copy(update=update)


def test_an_exchange_is_kept_with_the_replys_tools_and_usage(
    app: FastAPI, auth_client: TestClient
) -> None:
    use_agent(app, ToolAgent())
    chat_id = new_chat(auth_client)

    events = say(auth_client, chat_id, "Schedule my digest every morning")

    usage = {"input_tokens": 120, "output_tokens": 30, "cost_usd": 0.002, "cost_complete": True}
    assert events[-1] == {"type": "usage", "usage": usage}
    detail = auth_client.get(f"/api/chats/{chat_id}").json()
    assert detail["title"] == "Schedule my digest every morning"
    person, reply = detail["messages"]
    assert (person["role"], person["text"], person["tools"]) == (
        "user",
        "Schedule my digest every morning",
        [],
    )
    assert (reply["role"], reply["text"]) == ("assistant", "Scheduled it.")
    assert reply["tools"] == [
        {
            "tool": "create_schedule",
            "label": "Creating a schedule",
            "status": "finished",
            "detail": "Every day at 09:00 (Europe/Paris)",
            "action": {
                "kind": "schedule",
                "id": 7,
                "title": "Digest",
                "subtitle": "Every day at 09:00 (Europe/Paris)",
            },
        }
    ]
    assert reply["usage"] == usage
    assert detail["usage"] == usage
    assert auth_client.get("/api/chats").json()[0]["title"] == detail["title"]


def test_the_assistant_reads_what_the_chat_said_before(
    app: FastAPI, auth_client: TestClient
) -> None:
    agent = FakeAgent(chunks=["Done: ", "digest built."])
    use_agent(app, agent)
    chat_id = new_chat(auth_client)

    say(auth_client, chat_id, "Build a digest")
    # A kept chat's own messages are read: the history sent with it is not.
    ignored = [{"role": "user", "content": "ignored"}]
    say(auth_client, chat_id, "Make it weekly", history=ignored, timezone="Europe/Paris")

    first, second = agent.conversations
    assert (first.history, first.summary) == ((), "")
    assert second.history == (
        ChatTurn("user", "Build a digest"),
        ChatTurn("assistant", "Done: digest built."),
    )
    assert (second.timezone, second.summary) == ("Europe/Paris", "")


def test_the_oldest_messages_become_notes_once_the_history_is_full(
    app: FastAPI, auth_client: TestClient
) -> None:
    limits(app, chat_history_max_chars=30)
    agent = FakeAgent(chunks=["ok"])
    use_agent(app, agent)
    chat_id = new_chat(auth_client)

    say(auth_client, chat_id, "a" * 20)
    say(auth_client, chat_id, "b" * 20)  # 22 characters said before it: all read
    say(auth_client, chat_id, "c")  # 44: the first message is folded into notes

    assert agent.summaries == [("", (ChatTurn("user", "a" * 20),))]
    third = agent.conversations[2]
    assert third.summary == NOTES_1
    assert third.history == (
        ChatTurn("assistant", "ok"),
        ChatTurn("user", "b" * 20),
        ChatTurn("assistant", "ok"),
    )

    say(auth_client, chat_id, "d")  # what the notes do not cover still fits: no new notes

    assert len(agent.summaries) == 1
    assert agent.conversations[3].summary == NOTES_1
    assert agent.conversations[3].history[0] == ChatTurn("assistant", "ok")

    say(auth_client, chat_id, "e" * 20)  # 30 unread characters: fits exactly
    say(auth_client, chat_id, "f")  # 52: the next oldest join the notes, which are rewritten

    assert agent.summaries[1] == (
        NOTES_1,
        (ChatTurn("assistant", "ok"), ChatTurn("user", "b" * 20)),
    )
    assert agent.conversations[5].summary == "notes 2: 2 messages folded in"
    assert agent.conversations[5].history[0] == ChatTurn("assistant", "ok")
    with app.state.database.session() as db:
        chat = db.get(Chat, chat_id)
        assert chat is not None
        assert chat.summary == "notes 2: 2 messages folded in"
        assert chat.summary_through_id == chat.messages[2].id


def test_without_history_room_each_message_stands_alone(
    app: FastAPI, auth_client: TestClient
) -> None:
    limits(app, chat_history_max_chars=0)
    agent = FakeAgent()
    use_agent(app, agent)
    chat_id = new_chat(auth_client)

    say(auth_client, chat_id, "one")
    say(auth_client, chat_id, "two")

    assert agent.summaries == []
    assert (agent.conversations[1].history, agent.conversations[1].summary) == ((), "")
    # The chat still keeps everything that was said.
    assert len(auth_client.get(f"/api/chats/{chat_id}").json()["messages"]) == 4


def test_a_full_chat_takes_no_more_messages(app: FastAPI, auth_client: TestClient) -> None:
    limits(app, chat_max_messages=2)
    use_agent(app, FakeAgent())
    chat_id = new_chat(auth_client)
    say(auth_client, chat_id, "one")

    body = {"prompt": "two", "chat_id": chat_id}
    response = auth_client.post("/api/chat", json=body, headers=NDJSON)

    assert (response.status_code, response.json()["error"]) == (409, "chat_full")
    assert len(auth_client.get(f"/api/chats/{chat_id}").json()["messages"]) == 2


def test_a_reply_that_never_began_leaves_the_chat_as_it_was(
    app: FastAPI, auth_client: TestClient
) -> None:
    use_agent(app, FakeAgent(chunks=[]))
    chat_id = new_chat(auth_client)

    body = {"prompt": "hi", "chat_id": chat_id}
    response = auth_client.post("/api/chat", json=body, headers=NDJSON)

    assert response.status_code == 502
    assert auth_client.get(f"/api/chats/{chat_id}").json()["messages"] == []


def test_another_users_chat_cannot_be_written_to(
    app: FastAPI, auth_client: TestClient, session: Session
) -> None:
    use_agent(app, FakeAgent())
    neighbour = users.create(session, "neighbour", hash_password("neighbour-pass-1234", 1))
    theirs = repository.create(session, neighbour, "", Quota(10, ValidationFailed("no")))

    body = {"prompt": "hi", "chat_id": theirs.id}
    response = auth_client.post("/api/chat", json=body, headers=NDJSON)

    assert response.status_code == 404
    session.refresh(theirs)
    assert theirs.messages == []
