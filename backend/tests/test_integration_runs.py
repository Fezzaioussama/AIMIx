"""Integrations at work: pipeline runs that do or do not need one, and the
"Test connection" endpoint. MCP servers and DNS are faked."""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest
from exceptiongroup import ExceptionGroup
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from mcp import McpError
from mcp.types import ErrorData
from sqlalchemy.orm import Session

from api.deps import app_settings, host_resolver, secret_box
from api.models import Pipeline, User
from api.repositories import pipelines
from api.security import SecretBox
from api.services import mcp_discovery
from api.services.catalog import default_model_id
from api.services.multiagent import step_agent
from api.services.outbound import ResponseTooLarge
from tests.conftest import TEST_SETTINGS
from tests.mcp_fakes import TOOL_DESCRIPTION, DnsAnswer, FakeServers, ServerBehaviour, resolver
from tests.test_integration_tools import TOKEN, save_integration

URL = "/api/integrations"


@pytest.fixture(autouse=True)
def dns(app: FastAPI) -> dict[str, DnsAnswer]:
    table: dict[str, DnsAnswer] = {}
    app.dependency_overrides[host_resolver] = lambda: resolver(table)
    return table


def servers(monkeypatch: pytest.MonkeyPatch, behaviour: dict[str, ServerBehaviour]) -> FakeServers:
    fake = FakeServers(behaviour)
    monkeypatch.setattr(mcp_discovery, "MultiServerMCPClient", fake)
    return fake


def one_step_pipeline(session: Session, user: User, allowed_tools: list[str] | None) -> Pipeline:
    step = {
        "order": 1,
        "stage": 1,
        "prompt": "Look up {input}",
        "model": default_model_id(),
        "allowed_tools": allowed_tools,
    }
    changes = pipelines.PipelineChanges("CRM", steps=[step])
    return pipelines.create_with_steps(session, user, changes)


@pytest.fixture
def bound_tools(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Runs every step on a fake graph that answers at once; lists the tools it got."""
    bound: list[str] = []

    class FakeGraph:
        async def ainvoke(self, state: object, **kwargs: Any) -> dict[str, Any]:
            return {"messages": [AIMessage(content="Looked it up.")]}

    def fake_create_agent(model: object, tools: list[Any], **kwargs: Any) -> FakeGraph:
        bound.extend(item.name for item in tools)
        return FakeGraph()

    monkeypatch.setattr(step_agent, "create_agent", fake_create_agent)
    monkeypatch.setattr(
        step_agent,
        "get_agent_model",
        lambda profile, model_id=None: FakeMessagesListChatModel(responses=[]),
    )
    return bound


def test_a_run_that_does_not_need_a_failing_integration_still_works(
    auth_client: TestClient,
    session: Session,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
    bound_tools: list[str],
) -> None:
    save_integration(session, user, "crm")
    servers(monkeypatch, {"crm": httpx.ConnectError("down")})
    saved = one_step_pipeline(session, user, allowed_tools=None)

    response = auth_client.post(f"/api/pipelines/{saved.id}/run", json={"input": "Acme"})

    assert response.status_code == 200
    assert response.json()["final_output"] == "Looked it up."
    assert "calculator" in bound_tools
    assert not any(name.startswith("crm_") for name in bound_tools)


def test_a_step_gets_the_integration_tools_it_selected(
    auth_client: TestClient,
    session: Session,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
    bound_tools: list[str],
) -> None:
    save_integration(session, user, "crm")
    servers(monkeypatch, {"crm": ["search", "create_deal"]})
    saved = one_step_pipeline(session, user, allowed_tools=["crm_search"])

    response = auth_client.post(f"/api/pipelines/{saved.id}/run", json={"input": "Acme"})

    assert response.status_code == 200
    assert bound_tools == ["crm_search"]


def test_a_step_that_selected_a_failing_integrations_tool_fails(
    auth_client: TestClient, session: Session, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_integration(session, user, "crm")
    servers(monkeypatch, {"crm": httpx.ConnectError("down")})
    saved = one_step_pipeline(session, user, allowed_tools=["calculator", "crm_search"])
    monkeypatch.setattr(
        step_agent,
        "get_agent_model",
        lambda profile, model_id=None: FakeMessagesListChatModel(responses=[]),
    )

    response = auth_client.post(f"/api/pipelines/{saved.id}/run", json={"input": "Acme"})

    assert response.status_code == 502
    assert response.json() == {
        "error": "tool_unavailable",
        "detail": "A selected agent tool is unavailable: crm_search.",
    }


def test_testing_a_connection_lists_the_tools_agents_will_get(
    auth_client: TestClient, session: Session, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    integration_id = save_integration(session, user, "crm", enabled=False)
    fake = servers(monkeypatch, {"crm": ["search", "create_deal"]})

    response = auth_client.post(f"{URL}/{integration_id}/test")

    assert response.status_code == 200
    assert response.json() == {
        "tools": [
            {"name": "crm_search", "description": TOOL_DESCRIPTION},
            {"name": "crm_create_deal", "description": TOOL_DESCRIPTION},
        ]
    }
    assert fake.seen["crm"]["headers"] == {"Authorization": TOKEN}
    assert TOKEN not in response.text


def status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://crm.example/mcp")
    return httpx.HTTPStatusError("failed", request=request, response=httpx.Response(status))


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (httpx.ConnectError("refused"), "the connection to it failed"),
        (status_error(401), "it refused the sign-in (HTTP 401), so check the headers"),
        (ExceptionGroup("tasks", [status_error(404)]), "nothing was found at that URL (HTTP 404)"),
        (status_error(500), "it answered with HTTP 500"),
        (TimeoutError(), "it did not answer within the time limit"),
        (McpError(ErrorData(code=-32601, message="no")), "it answered with an MCP error"),
        (ValueError("odd"), "it did not answer as an MCP server"),
        (ResponseTooLarge("big"), "it sent an answer larger than the size limit"),
    ],
)
def test_a_failed_connection_test_says_why(
    auth_client: TestClient,
    session: Session,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: BaseException,
    reason: str,
) -> None:
    integration_id = save_integration(session, user, "crm")
    servers(monkeypatch, {"crm": error})

    with caplog.at_level(logging.WARNING):
        response = auth_client.post(f"{URL}/{integration_id}/test")

    assert response.status_code == 502
    assert response.json() == {
        "error": "tool_unavailable",
        "detail": f"Could not connect to crm: {reason}.",
    }
    assert "integration.test_failed" in caplog.text
    assert "crm-secret" not in caplog.text


def test_a_connection_test_checks_the_address_again(
    auth_client: TestClient,
    session: Session,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
    dns: dict[str, DnsAnswer],
) -> None:
    integration_id = save_integration(session, user, "crm")
    fake = servers(monkeypatch, {"crm": ["search"]})
    dns["crm.example"] = ["169.254.169.254"]

    response = auth_client.post(f"{URL}/{integration_id}/test")

    assert response.status_code == 400
    assert "crm.example is not a public address" in response.json()["detail"]
    assert fake.seen == {}


def test_a_connection_test_asks_again_for_header_values_it_cannot_read(
    app: FastAPI, auth_client: TestClient, session: Session, user: User
) -> None:
    integration_id = save_integration(session, user, "crm")
    app.dependency_overrides[secret_box] = lambda: SecretBox("a-rotated-secret-key")

    response = auth_client.post(f"{URL}/{integration_id}/test")

    assert response.status_code == 400
    assert response.json()["detail"].endswith("Enter each value again.")
    # The list still loads, so the values can be entered again.
    assert auth_client.get(URL).status_code == 200


#: Routes that make the server reach out to an MCP server or a DNS server.
REACHING_OUT = [
    ("POST", URL, {"name": "erp", "url": "https://erp.example/mcp"}),
    ("PATCH", URL + "/{id}", {"enabled": True}),
    ("POST", URL + "/{id}/test", None),
    ("GET", "/api/agent-tools", None),
]


@pytest.mark.parametrize(("method", "path", "payload"), REACHING_OUT)
def test_routes_that_reach_out_are_rate_limited_per_account(
    app: FastAPI,
    auth_client: TestClient,
    session: Session,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
) -> None:
    integration_id = save_integration(session, user, "crm")
    servers(monkeypatch, {"crm": ["search"]})
    limited = TEST_SETTINGS.model_copy(update={"user_rate_limit_requests": 2})
    app.dependency_overrides[app_settings] = lambda: limited
    url = path.format(id=integration_id)

    for _ in range(2):
        assert auth_client.request(method, url, json=payload).status_code < 429
    blocked = auth_client.request(method, url, json=payload)

    assert blocked.status_code == 429
    assert blocked.json()["error"] == "throttled"
