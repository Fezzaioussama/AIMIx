"""Saved pipeline steps execute as user-scoped LangGraph agents."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import ToolException, tool
from sqlalchemy.orm import Session

from api.exceptions import ToolUnavailable
from api.models import Pipeline, User
from api.repositories import pipelines
from api.services import agent as agent_service
from api.services import llm as llm_service
from api.services import pipeline_agents
from api.services.catalog import default_model_id
from llm.base import ProviderConfig


def tool_call_model() -> FakeMessagesListChatModel:
    return FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "increment", "args": {"number": 2}, "id": "call-1"}],
            ),
            AIMessage(content="Result is 3"),
        ]
    )


def test_tool_trace_records_error_without_tool_output() -> None:
    messages = [
        AIMessage(
            content="",
            tool_calls=[{"name": "docs_search", "args": {}, "id": "call-1"}],
        ),
        ToolMessage(content="private result", tool_call_id="call-1", status="error"),
    ]
    assert agent_service._tool_trace(messages) == [
        agent_service.ToolCallTrace(name="docs_search", status="error")
    ]


def saved_pipeline(session: Session, user: User, name: str, prompt: str) -> Pipeline:
    return pipelines.create_with_steps(
        session,
        user,
        name,
        [{"order": 1, "stage": 1, "prompt": prompt, "model": default_model_id()}],
    )


def test_step_model_overrides_chat_default(monkeypatch: pytest.MonkeyPatch) -> None:
    selected: list[str] = []

    def capture_model(provider: str, config: ProviderConfig) -> FakeMessagesListChatModel:
        selected.append(config.default_model)
        return FakeMessagesListChatModel(responses=[])

    monkeypatch.setattr(llm_service, "create_agent_model", capture_model)
    llm_service.get_agent_model("selected/model")
    assert selected == ["selected/model"]


def test_step_uses_its_model_and_discovered_tool(
    auth_client: TestClient,
    session: Session,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_model = default_model_id()
    saved = saved_pipeline(session, user, "Calculate", "Add one to {input}")
    called: list[int] = []
    selected: list[str | None] = []
    discovered: list[bool] = []
    bound_tools: list[str] = []

    @tool
    def increment(number: int) -> int:
        """Add one to a number."""
        called.append(number)
        return number + 1

    async def fake_discover(configured: object, native: list[Any], timeout: float) -> list[Any]:
        discovered.append(True)
        return [*native, increment]

    model = tool_call_model()

    def fake_model(model_id: str | None = None) -> FakeMessagesListChatModel:
        selected.append(model_id)
        return model

    def bind_tools(self: FakeMessagesListChatModel, tools: list[Any], **kw: Any) -> Any:
        bound_tools.extend(item.name for item in tools)
        return self

    monkeypatch.setattr(FakeMessagesListChatModel, "bind_tools", bind_tools)
    monkeypatch.setattr(agent_service, "discover_tools", fake_discover)
    monkeypatch.setattr(pipeline_agents, "get_agent_model", fake_model)

    response = auth_client.post(f"/api/pipelines/{saved.id}/run", json={"input": "2"})

    assert response.status_code == 200
    assert response.json()["final_output"] == "Result is 3"
    assert called == [2]
    assert selected == [default_model]
    assert discovered == [True]
    assert set(bound_tools) == {"list_pipelines", "inspect_pipeline", "increment"}
    assert response.json()["intermediate_results"][0]["tool_calls"] == [
        {"name": "increment", "status": "success"}
    ]


def test_step_role_and_tool_allowlist_reach_langgraph(
    auth_client: TestClient,
    session: Session,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = saved_pipeline(session, user, "Research", "Find {input}")
    saved.steps[0].role = "Researcher"
    saved.steps[0].allowed_tools = ["inspect_pipeline"]
    session.commit()
    observed: dict[str, Any] = {}

    class FakeGraph:
        async def ainvoke(self, state: object, **kwargs: Any) -> dict[str, Any]:
            return {"messages": [AIMessage(content="Research complete.")]}

    def fake_create_agent(model: object, tools: list[Any], **kwargs: Any) -> FakeGraph:
        observed["tools"] = [item.name for item in tools]
        observed["system_prompt"] = kwargs["system_prompt"]
        return FakeGraph()

    monkeypatch.setattr(agent_service, "create_agent", fake_create_agent)
    monkeypatch.setattr(pipeline_agents, "get_agent_model", lambda model_id=None: tool_call_model())
    response = auth_client.post(f"/api/pipelines/{saved.id}/run", json={"input": "facts"})
    assert response.status_code == 200
    assert observed["tools"] == ["inspect_pipeline"]
    assert "Researcher" in observed["system_prompt"]


def test_mcp_discovery_failure_stops_the_pipeline(
    auth_client: TestClient,
    session: Session,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = saved_pipeline(session, user, "Unavailable", "Use a tool on {input}")

    async def fake_discover(configured: object, native: list[Any], timeout: float) -> list[Any]:
        raise ToolUnavailable("An MCP server is unavailable.")

    monkeypatch.setattr(agent_service, "discover_tools", fake_discover)
    monkeypatch.setattr(
        pipeline_agents,
        "get_agent_model",
        lambda model_id=None: FakeMessagesListChatModel(responses=[]),
    )

    response = auth_client.post(f"/api/pipelines/{saved.id}/run", json={"input": "seed"})

    assert response.status_code == 502
    assert response.json()["error"] == "tool_unavailable"


def test_missing_selected_tool_is_reported(
    auth_client: TestClient,
    session: Session,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = saved_pipeline(session, user, "Missing tool", "Use {input}")
    saved.steps[0].allowed_tools = ["missing_tool"]
    session.commit()
    monkeypatch.setattr(pipeline_agents, "get_agent_model", lambda model_id=None: tool_call_model())
    response = auth_client.post(f"/api/pipelines/{saved.id}/run", json={"input": "seed"})
    assert response.status_code == 502
    assert response.json()["error"] == "tool_unavailable"


def test_tool_execution_error_is_reported(
    auth_client: TestClient,
    session: Session,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = saved_pipeline(session, user, "Failing tool", "Use {input}")
    saved.steps[0].allowed_tools = []
    session.commit()

    class FailingGraph:
        async def ainvoke(self, state: object, **kwargs: Any) -> dict[str, Any]:
            raise ToolException("failed")

    monkeypatch.setattr(agent_service, "create_agent", lambda model, tools, **kw: FailingGraph())
    monkeypatch.setattr(pipeline_agents, "get_agent_model", lambda model_id=None: tool_call_model())
    response = auth_client.post(f"/api/pipelines/{saved.id}/run", json={"input": "seed"})
    assert response.status_code == 502
    assert response.json()["error"] == "tool_unavailable"
