"""The approval gate in front of a real agent: an approved call acts; a declined,
unanswered or stopped one does not, and the agent is told. The owner can read
what is asked, and the logs never can."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest

from api.db import Database
from api.models import ApprovalStatus, Base, RunApproval, RunStatus, User
from api.repositories import integrations, runs
from api.repositories.integrations import IntegrationChanges
from api.services import agent_runtime
from api.services.agent_runtime import AgentLimits, AgentToolset
from api.services.agent_types import AgentOutcome, AgentTask, RunStepRef, ToolCallTrace
from api.services.approvals.decisions import ApprovalAnswer, answer
from api.services.approvals.gate import (
    ApprovalLimits,
    RunApprovalGate,
    ToolRequest,
    approval_limits,
)
from api.services.approvals.policy import ApprovalPolicy
from api.services.llm import LLMProfile
from api.services.mcp import MCPConnections
from api.services.multiagent.step_agent import (
    LangGraphStepAgent,
    PipelineAgentGenerator,
    StepAgentDependencies,
)
from api.services.run_recorder import cancelled, utcnow
from tests.approval_fakes import (
    FAST_LIMITS,
    ScriptedGate,
    ToolThenReport,
    approval_status,
    make_owner,
    make_pipeline,
    recording_tool,
    run_status,
    running_run,
)
from tests.conftest import TEST_SETTINGS

SEND = {"to": "ada@example.com"}
TASK = AgentTask("Send the invitation.", "m", "Sender", None)


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


async def next_request(database: Database, run_id: int) -> RunApproval:
    """Wait until the step's agent has asked, as a person watching the run would."""
    for _ in range(500):
        with database.session() as session:
            run = runs.load(session, run_id)
        assert run is not None
        if run.pending_approvals:
            assert run.status == RunStatus.WAITING
            return run.pending_approvals[0]
        await asyncio.sleep(0.01)
    raise AssertionError("the agent never asked")


async def reply_as(
    database: Database, owner: User, run_id: int, status: ApprovalStatus
) -> RunApproval:
    """The owner's answer to the next request."""
    approval = await next_request(database, run_id)
    with database.session() as session:
        answer(session, owner, ApprovalAnswer(run_id, approval.id, status))
    return approval


def step_agent(
    database: Database, run_id: int, calls: list[dict[str, Any]], limits: ApprovalLimits
) -> LangGraphStepAgent:
    """A step whose agent calls ``crm_send_email``, a tool that asks first."""
    policy = ApprovalPolicy(tool_names=frozenset({"crm_send_email"}))
    toolset = AgentToolset(MCPConnections(), [recording_tool("crm_send_email", calls)], policy)
    gate = RunApprovalGate(database, RunStepRef(run_id, 1), limits)
    return LangGraphStepAgent(
        ToolThenReport(tool="crm_send_email", arguments=SEND), toolset, AgentLimits(5, 9, 1), gate
    )


@pytest.mark.asyncio
async def test_an_approved_call_runs_the_tool(database: Database, owner: User, run_id: int) -> None:
    calls: list[dict[str, Any]] = []
    agent = step_agent(database, run_id, calls, FAST_LIMITS)

    outcome, asked = await asyncio.gather(
        agent.reply(TASK), reply_as(database, owner, run_id, ApprovalStatus.APPROVED)
    )

    assert calls == [SEND]
    assert outcome == AgentOutcome("Tool said: sent", [ToolCallTrace("crm_send_email", "success")])
    assert (asked.tool_name, asked.tool_source, asked.step_order) == ("crm_send_email", "AIMIx", 1)
    assert (asked.arguments, asked.arguments_truncated) == (SEND, False)
    assert asked.tool_description == "Send an email to a contact."
    assert approval_status(database, asked.id) == ApprovalStatus.APPROVED
    assert run_status(database, run_id) == RunStatus.RUNNING


@pytest.mark.asyncio
async def test_a_declined_call_does_not_run_the_tool_and_the_agent_is_told(
    database: Database, owner: User, run_id: int
) -> None:
    calls: list[dict[str, Any]] = []
    agent = step_agent(database, run_id, calls, FAST_LIMITS)

    outcome, asked = await asyncio.gather(
        agent.reply(TASK), reply_as(database, owner, run_id, ApprovalStatus.DECLINED)
    )

    assert calls == []
    assert outcome.output.startswith("Tool said: The user declined this action.")
    assert outcome.tool_calls == [ToolCallTrace("crm_send_email", "error")]
    assert approval_status(database, asked.id) == ApprovalStatus.DECLINED
    assert run_status(database, run_id) == RunStatus.RUNNING


@pytest.mark.asyncio
async def test_an_unanswered_call_expires_and_counts_as_declined(
    database: Database, run_id: int
) -> None:
    calls: list[dict[str, Any]] = []
    agent = step_agent(database, run_id, calls, replace(FAST_LIMITS, timeout_seconds=0.05))

    outcome = await agent.reply(TASK)

    assert calls == []
    assert "did not answer in time" in outcome.output
    assert outcome.tool_calls == [ToolCallTrace("crm_send_email", "error")]
    with database.session() as session:
        run = runs.load(session, run_id)
    assert run is not None and run.pending_approvals == []
    assert run.status == RunStatus.RUNNING


@pytest.mark.asyncio
async def test_stopping_the_wait_expires_the_request(database: Database, run_id: int) -> None:
    gate = RunApprovalGate(database, RunStepRef(run_id, 1), FAST_LIMITS)
    waiting = asyncio.create_task(gate.ask(ToolRequest(recording_tool("t", []), "crm", SEND)))
    asked = await next_request(database, run_id)

    waiting.cancel()

    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert approval_status(database, asked.id) == ApprovalStatus.EXPIRED
    assert run_status(database, run_id) == RunStatus.RUNNING


@pytest.mark.asyncio
async def test_a_step_cannot_ask_once_its_run_was_stopped(database: Database, run_id: int) -> None:
    with database.session() as session:
        runs.end(session, run_id, cancelled(), utcnow())
    gate = RunApprovalGate(database, RunStepRef(run_id, 1), FAST_LIMITS)

    status = await gate.ask(ToolRequest(recording_tool("t", []), "crm", SEND))

    assert status == ApprovalStatus.EXPIRED
    with database.session() as session:
        run = runs.load(session, run_id)
    assert run is not None and run.status == RunStatus.CANCELLED
    assert run.pending_approvals == []


@pytest.mark.asyncio
async def test_a_tool_that_does_not_ask_runs_without_the_gate(
    database: Database, run_id: int
) -> None:
    calls: list[dict[str, Any]] = []
    policy = ApprovalPolicy(tool_names=frozenset({"crm_send_email"}))
    tools = [recording_tool("lookup", calls), recording_tool("crm_send_email", [])]
    gate = ScriptedGate()
    agent = LangGraphStepAgent(
        ToolThenReport(tool="lookup", arguments=SEND),
        AgentToolset(MCPConnections(), tools, policy),
        AgentLimits(5, 9, 1),
        gate,
    )

    outcome = await agent.reply(TASK)

    assert outcome.output == "Tool said: sent"
    assert calls == [SEND]
    assert gate.asked == []


@pytest.mark.asyncio
async def test_the_gate_is_asked_about_the_call_as_the_model_made_it(
    database: Database, run_id: int
) -> None:
    calls: list[dict[str, Any]] = []
    policy = ApprovalPolicy(tool_names=frozenset({"crm_send_email"}))
    gate = ScriptedGate([ApprovalStatus.APPROVED])
    agent = LangGraphStepAgent(
        ToolThenReport(tool="crm_send_email", arguments=SEND),
        AgentToolset(MCPConnections(), [recording_tool("crm_send_email", calls)], policy),
        AgentLimits(5, 9, 1),
        gate,
    )

    await agent.reply(TASK)

    [asked] = gate.asked
    assert (asked.tool.name, asked.source, dict(asked.arguments)) == (
        "crm_send_email",
        "AIMIx",
        SEND,
    )
    assert calls == [SEND]


@pytest.mark.asyncio
async def test_the_owner_can_read_the_arguments_and_the_logs_never_can(
    database: Database, owner: User, run_id: int, caplog: pytest.LogCaptureFixture
) -> None:
    gate = RunApprovalGate(database, RunStepRef(run_id, 1), FAST_LIMITS)
    secret = {"to": "secret-person@example.com", "body": "the launch is on the 9th"}

    with caplog.at_level(logging.INFO):
        _, asked = await asyncio.gather(
            gate.ask(ToolRequest(recording_tool("crm_send_email", []), "crm", secret)),
            reply_as(database, owner, run_id, ApprovalStatus.APPROVED),
        )

    assert asked.arguments == secret
    assert f"approval.requested run_id={run_id} step=1 tool=crm_send_email" in caplog.text
    assert f"approval.decided run_id={run_id} approval_id={asked.id} step=1" in caplog.text
    assert "outcome=approved" in caplog.text
    assert "secret-person" not in caplog.text and "launch is on" not in caplog.text


def test_a_request_never_waits_longer_than_a_step_may_last() -> None:
    longer = TEST_SETTINGS.model_copy(
        update={"approval_timeout_seconds": 1800.0, "agent_timeout_seconds": 600.0}
    )
    shorter = TEST_SETTINGS.model_copy(
        update={"approval_timeout_seconds": 60.0, "agent_timeout_seconds": 600.0}
    )

    assert approval_limits(longer).timeout_seconds == 600.0
    assert approval_limits(shorter).timeout_seconds == 60.0
    assert (
        approval_limits(shorter).arguments_max_chars == TEST_SETTINGS.approval_arguments_max_chars
    )


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
