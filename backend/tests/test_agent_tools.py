"""Native chat tools use the same ownership and run rules as pipeline endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.exceptions import NotFound, ValidationFailed
from api.models import Pipeline, User
from api.repositories import pipelines, users
from api.security import hash_password
from api.services import agent as agent_service
from api.services import agent_tools
from api.services.agent_tools import built_in_tools
from tests.conftest import FakeProvider


def test_native_tools_list_inspect_and_run_owned_pipeline(
    app: FastAPI, session: Session, user: User
) -> None:
    saved = pipelines.create_with_steps(
        session,
        user,
        "Summarise",
        [{"order": 1, "stage": 1, "title": "Summary", "prompt": "Summarise {input}", "model": "m"}],
    )
    provider = FakeProvider(reply="summary")
    listing, inspect, run = built_in_tools(app.state.database, user, lambda: provider)

    assert listing.name == "list_pipelines"
    assert listing.invoke({}) == [{"id": saved.id, "name": "Summarise", "step_count": 1}]
    details = inspect.invoke({"pipeline_id": saved.id})
    assert details["steps"][0]["prompt"] == "Summarise {input}"
    assert run.invoke({"pipeline_id": saved.id, "input_text": "hello"})["final_output"] == "summary"
    assert provider.calls == [("Summarise hello", "m")]


def test_native_tools_cannot_read_or_run_another_users_pipeline(
    app: FastAPI, session: Session, user: User
) -> None:
    stranger = users.create(session, "stranger", hash_password("password-123", 1))
    theirs = pipelines.create_with_steps(
        session,
        stranger,
        "Private",
        [{"order": 1, "stage": 1, "prompt": "private {input}", "model": "m"}],
    )
    provider = FakeProvider()
    listing, inspect, run = built_in_tools(app.state.database, user, lambda: provider)

    assert listing.invoke({}) == []
    with pytest.raises(NotFound):
        inspect.invoke({"pipeline_id": theirs.id})
    with pytest.raises(NotFound):
        run.invoke({"pipeline_id": theirs.id, "input_text": "hello"})
    assert provider.calls == []


def test_native_run_rejects_blank_input(app: FastAPI, user: User) -> None:
    run = built_in_tools(app.state.database, user, FakeProvider)[2]
    with pytest.raises(ValidationFailed):
        run.invoke({"pipeline_id": 1, "input_text": "   "})


def test_authenticated_chat_can_call_a_native_tool(
    app: FastAPI,
    auth_client: TestClient,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    with app.state.database.session() as session:
        owner = session.get(User, user.id)
        assert owner is not None
        pipelines.create_with_steps(session, owner, "Mine", [])
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="", tool_calls=[{"name": "list_pipelines", "args": {}, "id": "call-1"}]
            ),
            AIMessage(content="Found your pipeline."),
        ]
    )
    monkeypatch.setattr(FakeMessagesListChatModel, "bind_tools", lambda self, tools, **kw: self)
    monkeypatch.setattr(agent_service, "get_agent_model", lambda: model)
    seen_users: list[int] = []
    original = agent_tools.repository.for_user

    def tracked_list(db_session: Session, owner: User) -> list[Pipeline]:
        seen_users.append(owner.id)
        return original(db_session, owner)

    monkeypatch.setattr(agent_tools.repository, "for_user", tracked_list)
    response = auth_client.post("/api/chat", json={"prompt": "List my pipelines"})
    assert response.status_code == 200
    assert response.text == "Found your pipeline."
    assert seen_users == [user.id]
