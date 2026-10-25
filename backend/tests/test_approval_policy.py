"""Which tool calls ask first: the policy, the one place that applies it to an
agent's tools, and the chat, which has no run to pause."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from langchain_core.messages import AIMessageChunk
from langchain_core.tools import BaseTool
from sqlalchemy.orm import Session

from api.models import User
from api.repositories import integrations, users
from api.repositories.integrations import IntegrationChanges
from api.security import hash_password
from api.services import agent as agent_service
from api.services import agent_runtime
from api.services.agent import LangGraphChatAgent
from api.services.agent_runtime import AgentLimits, AgentToolset
from api.services.approvals.guard import guard_tools
from api.services.approvals.middleware import ApprovalMiddleware
from api.services.approvals.policy import NO_APPROVALS, ApprovalPolicy, approval_policy_for
from api.services.mcp import MCPConnections
from api.services.tool_catalog import NATIVE_SOURCE, OPERATOR_MCP_SOURCE, source_of
from config.settings import Settings
from tests.approval_fakes import ScriptedGate, integration_tool
from tests.conftest import TEST_SETTINGS
from tests.mcp_fakes import fake_tool


def save_integration(session: Session, owner: User, name: str, **fields: Any) -> None:
    changes = IntegrationChanges(name=name, url=f"https://{name}.example/mcp", **fields)
    integrations.create(session, owner, changes)


def policy_for(app: FastAPI, user: User, **settings: Any) -> ApprovalPolicy:
    resolved = TEST_SETTINGS.model_copy(update=settings)
    return approval_policy_for(app.state.database, user, resolved)


def test_by_default_nothing_asks_in_the_tests_and_everything_outside_asks() -> None:
    assert NO_APPROVALS.asks("crm_send_email", "crm") is False
    defaults = Settings(_env_file=None)
    assert defaults.mcp_require_approval is True
    assert defaults.agent_approval_tools == []
    assert defaults.approval_timeout_seconds == 1800
    assert defaults.approval_timeout_seconds < defaults.agent_timeout_seconds


def test_the_approval_tools_setting_is_a_comma_list() -> None:
    settings = Settings(_env_file=None, AGENT_APPROVAL_TOOLS=" save_artifact , run_python ,")  # type: ignore[arg-type]

    assert settings.agent_approval_tools == ["save_artifact", "run_python"]


def test_operator_servers_ask_unless_the_setting_turns_it_off(app: FastAPI, user: User) -> None:
    asks = policy_for(app, user, mcp_require_approval=True)
    silent = policy_for(app, user, mcp_require_approval=False)

    assert asks.asks("docs_search", OPERATOR_MCP_SOURCE)
    assert not asks.asks("calculator", NATIVE_SOURCE)
    assert not silent.asks("docs_search", OPERATOR_MCP_SOURCE)


def test_an_integration_asks_until_its_own_switch_is_off(
    app: FastAPI, session: Session, user: User
) -> None:
    save_integration(session, user, "crm")
    save_integration(session, user, "sales", require_approval=False)
    save_integration(session, user, "paused", enabled=False)

    policy = policy_for(app, user)

    assert policy.sources == frozenset({"crm"})
    assert policy.asks("crm_send_email", "crm")
    assert not policy.asks("sales_update_deal", "sales")


def test_only_the_users_own_integrations_count(app: FastAPI, session: Session, user: User) -> None:
    stranger = users.create(session, "stranger", hash_password("x-pass-2891", 1))
    save_integration(session, stranger, "theirs")

    assert policy_for(app, user).sources == frozenset()


def test_a_built_in_tool_can_be_made_to_ask_by_name(app: FastAPI, user: User) -> None:
    policy = policy_for(app, user, agent_approval_tools=["save_artifact"])

    assert policy.asks("save_artifact", NATIVE_SOURCE)
    assert not policy.asks("calculator", NATIVE_SOURCE)


def test_a_tool_is_sourced_from_aimix_an_integration_or_the_operator() -> None:
    native = {"calculator"}

    assert source_of(fake_tool("calculator"), native) == NATIVE_SOURCE
    assert source_of(integration_tool("crm_search", "crm"), native) == "crm"
    assert source_of(fake_tool("docs_search"), native) == OPERATOR_MCP_SOURCE


def toolset(policy: ApprovalPolicy) -> tuple[AgentToolset, list[BaseTool]]:
    calculator = fake_tool("calculator")
    tools = [calculator, integration_tool("crm_send_email", "crm"), fake_tool("docs_search")]
    return AgentToolset(MCPConnections(), [calculator], policy), tools


def test_a_recorded_step_keeps_every_tool_and_gates_those_that_ask() -> None:
    policy = ApprovalPolicy(sources=frozenset({"crm"}), tool_names=frozenset({"calculator"}))
    configured, tools = toolset(policy)

    guarded = guard_tools(configured, tools, ScriptedGate())

    assert guarded.tools == tools
    assert guarded.asking == {"calculator": NATIVE_SOURCE, "crm_send_email": "crm"}
    assert [type(item) for item in guarded.middleware] == [ApprovalMiddleware]


def test_nothing_that_asks_means_no_middleware_at_all() -> None:
    configured, tools = toolset(NO_APPROVALS)

    guarded = guard_tools(configured, tools, ScriptedGate())

    assert (guarded.tools, guarded.middleware, guarded.asking) == (tools, [], {})


def test_where_nobody_can_be_asked_the_tools_that_ask_are_not_offered() -> None:
    configured, tools = toolset(ApprovalPolicy(sources=frozenset({OPERATOR_MCP_SOURCE})))

    guarded = guard_tools(configured, tools, gate=None)

    assert [item.name for item in guarded.tools] == ["calculator", "crm_send_email"]
    assert guarded.middleware == []
    assert guarded.asking == {"docs_search": OPERATOR_MCP_SOURCE}


@pytest.mark.asyncio
async def test_the_chat_is_not_offered_the_tools_that_ask(monkeypatch: pytest.MonkeyPatch) -> None:
    configured, tools = toolset(ApprovalPolicy(sources=frozenset({"crm"})))
    offered: list[list[str]] = []

    async def discover(connections: object, native: list[Any], timeout: float) -> list[Any]:
        return tools

    class FakeGraph:
        async def astream(self, state: object, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            yield {
                "type": "messages",
                "data": (AIMessageChunk(content="Hi"), {"langgraph_node": "model"}),
            }

    def create_agent(model: object, offered_tools: list[BaseTool]) -> FakeGraph:
        offered.append([item.name for item in offered_tools])
        return FakeGraph()

    monkeypatch.setattr(agent_runtime, "discover_tools", discover)
    monkeypatch.setattr(agent_service, "create_agent", create_agent)
    agent = LangGraphChatAgent(object(), configured, AgentLimits(10, 9, 1))  # type: ignore[arg-type]

    assert [part async for part in agent.stream("hello")] == ["Hi"]
    assert offered == [["calculator", "docs_search"]]
