"""Native chat tools use the same ownership and run rules as pipeline endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.tools import BaseTool
from sqlalchemy.orm import Session

from api.exceptions import NotFound, ValidationFailed
from api.models import Pipeline, User
from api.repositories import pipelines, users
from api.repositories.pipelines import PipelineChanges
from api.security import hash_password
from api.services import agent as agent_service
from api.services import agent_tools
from api.services.agent_tools import built_in_tools
from api.services.multiagent.contracts import StepAgent
from tests.conftest import FakeProvider, use_pipeline_generator


def chat_tools(app: FastAPI, user: User, agent: StepAgent) -> dict[str, BaseTool]:
    tools = built_in_tools(app.state.database, user, lambda: agent)
    return {item.name: item for item in tools}


def one_step(name: str, prompt: str, **fields: Any) -> PipelineChanges:
    """A pipeline of one step on model ``m``; ``fields`` may add ``inputs`` or step keys."""
    inputs = fields.pop("inputs", [])
    step = {"order": 1, "stage": 1, "prompt": prompt, "model": "m", **fields}
    return PipelineChanges(name, inputs=inputs, steps=[step])


def test_native_tools_list_inspect_and_run_owned_pipeline(
    app: FastAPI, session: Session, user: User
) -> None:
    saved = pipelines.create_with_steps(
        session, user, one_step("Summarise", "Summarise {input}", title="Summary")
    )
    provider = FakeProvider(reply="summary")
    tools = chat_tools(app, user, provider)
    listing, inspect, run = (
        tools[name] for name in ("list_pipelines", "inspect_pipeline", "run_pipeline")
    )

    assert listing.name == "list_pipelines"
    assert listing.invoke({}) == [{"id": saved.id, "name": "Summarise", "step_count": 1}]
    details = inspect.invoke({"pipeline_id": saved.id})
    assert details["steps"][0]["prompt"] == "Summarise {input}"
    assert (details["inputs"], details["steps"][0]["expected_output"]) == ([], "")
    assert run.invoke({"pipeline_id": saved.id, "input_text": "hello"})["final_output"] == "summary"
    assert provider.calls == [("Summarise hello", "m")]


def test_native_tools_inspect_and_run_a_pipeline_with_named_inputs(
    app: FastAPI, session: Session, user: User
) -> None:
    topic = {"name": "topic", "label": "Topic", "description": "What to write about"}
    saved = pipelines.create_with_steps(
        session, user, one_step("Post", "Write about {topic}", inputs=[topic])
    )
    provider = FakeProvider(reply="post")
    tools = chat_tools(app, user, provider)

    assert tools["inspect_pipeline"].invoke({"pipeline_id": saved.id})["inputs"] == [topic]
    result = tools["run_pipeline"].invoke({"pipeline_id": saved.id, "inputs": {"topic": "bees"}})
    assert result["final_output"] == "post"
    assert provider.calls == [("Write about bees", "m")]


def test_native_tools_cannot_read_or_run_another_users_pipeline(
    app: FastAPI, session: Session, user: User
) -> None:
    stranger = users.create(session, "stranger", hash_password("password-123", 1))
    theirs = pipelines.create_with_steps(session, stranger, one_step("Private", "private {input}"))
    provider = FakeProvider()
    tools = chat_tools(app, user, provider)
    listing, inspect, run = (
        tools[name] for name in ("list_pipelines", "inspect_pipeline", "run_pipeline")
    )

    assert listing.invoke({}) == []
    with pytest.raises(NotFound):
        inspect.invoke({"pipeline_id": theirs.id})
    with pytest.raises(NotFound):
        run.invoke({"pipeline_id": theirs.id, "input_text": "hello"})
    assert provider.calls == []


def test_native_run_rejects_blank_input(app: FastAPI, session: Session, user: User) -> None:
    saved = pipelines.create_with_steps(session, user, one_step("Echo", "{input}"))
    provider = FakeProvider()
    run = chat_tools(app, user, provider)["run_pipeline"]
    with pytest.raises(ValidationFailed, match="must not be blank"):
        run.invoke({"pipeline_id": saved.id, "input_text": "   "})
    assert provider.calls == []


def test_chat_tools_include_the_built_in_toolbox(app: FastAPI, user: User) -> None:
    assert {"fetch_url", "calculator", "current_datetime"} <= set(
        chat_tools(app, user, FakeProvider())
    )


def test_workspace_tools_are_scoped_to_the_authenticated_user(
    app: FastAPI, session: Session, user: User, tmp_path: Path
) -> None:
    stranger = users.create(session, "workspace-stranger", hash_password("password-123", 1))
    settings = agent_tools.get_settings().model_copy(
        update={
            "workspace_dir": tmp_path,
            "agent_builtin_tools": ["read_workspace_file", "save_artifact"],
        }
    )
    mine = {
        tool.name: tool for tool in agent_tools.native_tools(app.state.database, user, settings)
    }
    theirs = {
        tool.name: tool for tool in agent_tools.native_tools(app.state.database, stranger, settings)
    }

    mine["save_artifact"].invoke({"path": "private.txt", "content": "owner secret"})

    assert mine["read_workspace_file"].invoke({"path": "private.txt"}) == "owner secret"
    denied = theirs["read_workspace_file"].invoke({"path": "private.txt"})
    assert "does not exist" in denied
    assert "owner secret" not in denied


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
        pipelines.create_with_steps(session, owner, PipelineChanges("Mine", steps=[]))
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="", tool_calls=[{"name": "list_pipelines", "args": {}, "id": "call-1"}]
            ),
            AIMessage(content="Found your pipeline."),
        ]
    )
    monkeypatch.setattr(FakeMessagesListChatModel, "bind_tools", lambda self, tools, **kw: self)
    monkeypatch.setattr(agent_service, "get_agent_model", lambda profile: model)
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


def test_chat_can_run_a_pipeline_through_the_graph(
    app: FastAPI,
    auth_client: TestClient,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    with app.state.database.session() as db_session:
        owner = db_session.get(User, user.id)
        assert owner is not None
        saved = pipelines.create_with_steps(
            db_session, owner, one_step("Summary", "Summarise {input}")
        )
    provider = FakeProvider(reply="summary")
    use_pipeline_generator(app, provider)
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "run_pipeline",
                        "args": {"pipeline_id": saved.id, "input_text": "hello"},
                        "id": "call-1",
                    }
                ],
            ),
            AIMessage(content="Pipeline complete."),
        ]
    )
    monkeypatch.setattr(FakeMessagesListChatModel, "bind_tools", lambda self, tools, **kw: self)
    monkeypatch.setattr(agent_service, "get_agent_model", lambda profile: model)

    response = auth_client.post("/api/chat", json={"prompt": "Run my summary pipeline"})

    assert response.status_code == 200
    assert response.text == "Pipeline complete."
    assert provider.calls == [("Summarise hello", "m")]
