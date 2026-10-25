"""What a step agent does with its gate: a tool that does not ask never meets it,
the gate hears the call as the model made it, and the real step-agent factory
wires the policy of the user's integrations and the step's own gate."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest

from api.db import Database
from api.models import ApprovalStatus, Base, User
from api.repositories import integrations, runs
from api.repositories.integrations import IntegrationChanges
from api.services import agent_runtime
from api.services.agent_runtime import AgentLimits, AgentToolset
from api.services.agent_types import RunStepRef, ToolCallTrace
from api.services.approvals.policy import ApprovalPolicy
from api.services.llm import LLMProfile
from api.services.mcp import MCPConnections
from api.services.multiagent.step_agent import (
    LangGraphStepAgent,
    PipelineAgentGenerator,
    StepAgentDependencies,
    StepServices,
)
from tests.approval_fakes import (
    SEND,
    TASK,
    ScriptedGate,
    ToolThenReport,
    make_owner,
    make_pipeline,
    recording_tool,
    reply_as,
    running_run,
)
from tests.conftest import TEST_SETTINGS


@pytest.fixture
def database() -> Iterator[Database]:
    db = Database("sqlite://")
    Base.metadata.create_all(db.engine)
    yield db
    db.engine.dispose()


@pytest.fixture
def owner(database: Database) -> User:
    return make_owner(database)


@pytest.fixture
def run_id(database: Database, owner: User) -> int:
    return running_run(database, owner, make_pipeline(database, owner))


def scripted_agent(
    model_tool: str, tools: list[Any], gate: ScriptedGate, asking: set[str]
) -> LangGraphStepAgent:
    """A step agent whose model calls ``model_tool``; ``asking`` names the tools that ask first."""
    policy = ApprovalPolicy(tool_names=frozenset(asking))
    return LangGraphStepAgent(
        ToolThenReport(tool=model_tool, arguments=SEND),
        AgentToolset(MCPConnections(), tools, policy),
        AgentLimits(5, 9, 1),
        StepServices(gate=gate),
    )


@pytest.mark.asyncio
async def test_a_tool_that_does_not_ask_runs_without_the_gate() -> None:
    calls: list[dict[str, Any]] = []
    tools = [recording_tool("lookup", calls), recording_tool("crm_send_email", [])]
    gate = ScriptedGate()

    outcome = await scripted_agent("lookup", tools, gate, {"crm_send_email"}).reply(TASK)

    assert outcome.output == "Tool said: sent"
    assert calls == [SEND]
    assert gate.asked == []


@pytest.mark.asyncio
async def test_the_gate_is_asked_about_the_call_as_the_model_made_it() -> None:
    calls: list[dict[str, Any]] = []
    gate = ScriptedGate([ApprovalStatus.APPROVED])
    tools = [recording_tool("crm_send_email", calls)]

    await scripted_agent("crm_send_email", tools, gate, {"crm_send_email"}).reply(TASK)

    [asked] = gate.asked
    assert (asked.tool.name, asked.source, dict(asked.arguments)) == (
        "crm_send_email",
        "AIMIx",
        SEND,
    )
    assert calls == [SEND]


def generator(database: Database, owner: User, model: ToolThenReport) -> PipelineAgentGenerator:
    """The real step-agent factory, with a scripted model and quick approvals."""
    settings = TEST_SETTINGS.model_copy(
        update={
            "mcp_require_approval": True,
            "approval_timeout_seconds": 5.0,
            "agent_timeout_seconds": 10.0,
        }
    )
    dependencies = StepAgentDependencies(lambda model_id: model, settings)
    return PipelineAgentGenerator(database, owner, LLMProfile("openrouter", "m"), dependencies)


@pytest.fixture
def crm_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """The user's integration ``crm`` offers ``crm_send_email``; its calls land here."""
    calls: list[dict[str, Any]] = []
    tool = recording_tool("crm_send_email", calls, integration="crm")

    async def discover(connections: object, native: list[Any], timeout: float) -> list[Any]:
        return [*native, tool]

    monkeypatch.setattr(agent_runtime, "discover_tools", discover)
    return calls


@pytest.mark.asyncio
async def test_a_pipeline_step_asks_before_an_integration_tool_acts(
    database: Database, owner: User, run_id: int, crm_calls: list[dict[str, Any]]
) -> None:
    with database.session() as session:
        integrations.create(session, owner, IntegrationChanges("crm", "https://crm.example/mcp"))
    agent = generator(database, owner, ToolThenReport(tool="crm_send_email", arguments=SEND))
    task = replace(TASK, run_step=RunStepRef(run_id, 1))

    outcome, asked = await asyncio.gather(
        agent.execute(task), reply_as(database, owner, run_id, ApprovalStatus.APPROVED)
    )

    assert crm_calls == [SEND]
    assert outcome.output == "Tool said: sent"
    assert (asked.tool_source, asked.tool_name) == ("crm", "crm_send_email")


@pytest.mark.asyncio
async def test_an_integration_the_owner_trusts_acts_at_once(
    database: Database, owner: User, run_id: int, crm_calls: list[dict[str, Any]]
) -> None:
    with database.session() as session:
        trusted = IntegrationChanges("crm", "https://crm.example/mcp", require_approval=False)
        integrations.create(session, owner, trusted)
    agent = generator(database, owner, ToolThenReport(tool="crm_send_email", arguments=SEND))

    outcome = await agent.execute(replace(TASK, run_step=RunStepRef(run_id, 1)))

    assert crm_calls == [SEND]
    assert outcome.output == "Tool said: sent"
    with database.session() as session:
        run = runs.load(session, run_id)
    assert run is not None and run.pending_approvals == []


@pytest.mark.asyncio
async def test_outside_a_recorded_run_the_tools_that_ask_are_not_offered(
    database: Database, owner: User, crm_calls: list[dict[str, Any]]
) -> None:
    with database.session() as session:
        integrations.create(session, owner, IntegrationChanges("crm", "https://crm.example/mcp"))
    agent = generator(database, owner, ToolThenReport(tool="crm_send_email", arguments=SEND))

    outcome = await agent.execute(TASK)

    assert crm_calls == []
    assert outcome.tool_calls == [ToolCallTrace("crm_send_email", "error")]
