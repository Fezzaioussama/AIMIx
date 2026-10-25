"""Builders shared by the approval-gate tests: runs with requests waiting, a
scripted gate, tools that record their calls, and a chat model that calls a tool
and then reports its result.

Nothing here waits for real: requests expire in fractions of a second.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator, Sequence
from concurrent.futures import Future
from datetime import timedelta
from pathlib import Path
from typing import Any, TypeVar

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool, StructuredTool
from sqlalchemy.orm import Session

from api.db import Database
from api.models import ApprovalStatus, Base, Pipeline, RunApproval, RunStatus, User
from api.repositories import approvals, pipelines, runs, users
from api.repositories.pipelines import PipelineChanges
from api.services.agent_types import AgentOutcome, AgentTask, ToolCallTrace
from api.services.approvals.decisions import ApprovalAnswer, answer
from api.services.approvals.gate import ApprovalLimits, RunApprovalGate, ToolRequest
from api.services.mcp_discovery import INTEGRATION_KEY
from api.services.run_recorder import utcnow
from api.services.runs import RunService, RunStart
from tests.conftest import FakeProvider
from tests.mcp_fakes import fake_tool

T = TypeVar("T")

#: A request's arguments as the tests send them.
ARGUMENTS = {"to": "ada@example.com", "subject": "Launch"}
#: What a model passes to the recording tool, and the task of a step's agent.
SEND = {"to": "ada@example.com"}
TASK = AgentTask("Send the invitation.", "m", "Sender", None)
#: A gate that gives an owner a moment, and never a real wait.
FAST_LIMITS = ApprovalLimits(
    timeout_seconds=5.0, poll_seconds=0.01, arguments_max_chars=200, description_max_chars=300
)


def file_database(directory: Path) -> Database:
    """A fresh file database: one connection per thread, as the real app has."""
    database = Database(f"sqlite:///{directory / 'approvals.sqlite3'}")
    Base.metadata.create_all(database.engine)
    return database


def make_owner(database: Database, name: str = "runner") -> User:
    with database.session() as session:
        return users.create(session, name, "hash")


def make_pipeline(database: Database, owner: User, stages: Sequence[int] = (1,)) -> Pipeline:
    """Step ``n`` (from 1) has role ``role-n`` and runs in ``stages[n - 1]``."""
    steps = [
        {"order": n, "stage": stage, "prompt": f"p{n} {{input}}", "model": "m", "role": f"role-{n}"}
        for n, stage in enumerate(stages, start=1)
    ]
    with database.session() as session:
        return pipelines.create_with_steps(session, owner, PipelineChanges("Flow", steps=steps))


class ParkedExecutor:
    """Saves runs without executing them, so a test sets their state by hand."""

    def submit(self, key: int, job: Callable[[], Awaitable[T]]) -> Future[T]:
        return Future()

    def cancel(self, key: int) -> None:
        return None

    def settled(self, key: int) -> bool:
        return True

    def shutdown(self) -> None:
        return None


def running_run(database: Database, owner: User, pipeline: Pipeline) -> int:
    """A saved run of ``pipeline``, running as if its job had begun; its id."""
    service = RunService(database, ParkedExecutor(), max_parallel_steps=4)
    run = service.start(owner, pipeline, RunStart("go"), FakeProvider()).run
    with database.session() as session:
        runs.set_status(session, run.id, [RunStatus.QUEUED], {"status": RunStatus.RUNNING})
    return run.id


def request_approval(
    session: Session, run_id: int, expires_in: timedelta = timedelta(minutes=5), step: int = 1
) -> RunApproval:
    """A pending request for ``crm_send_email``, as a step's gate records it."""
    now = utcnow()
    new = approvals.NewApproval(
        run_id=run_id,
        step_order=step,
        tool_name="crm_send_email",
        tool_source="crm",
        tool_description="Send an email to a contact.",
        arguments=dict(ARGUMENTS),
        arguments_truncated=False,
        created_at=now,
        expires_at=now + expires_in,
    )
    approval = approvals.ask(session, new)
    assert approval is not None
    return approval


def approval_status(database: Database, approval_id: int) -> ApprovalStatus | None:
    with database.session() as session:
        return approvals.status_of(session, approval_id)


def run_status(database: Database, run_id: int) -> RunStatus:
    with database.session() as session:
        run = runs.load(session, run_id)
    assert run is not None
    return run.status


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


class ScriptedGate:
    """An ``ApprovalGate`` that answers from a list and remembers what it was asked."""

    def __init__(self, answers: Sequence[ApprovalStatus] = ()) -> None:
        self._answers: Iterator[ApprovalStatus] = iter(answers)
        self.asked: list[ToolRequest] = []

    async def ask(self, request: ToolRequest) -> ApprovalStatus:
        self.asked.append(request)
        return next(self._answers)


def integration_tool(name: str, integration: str) -> BaseTool:
    """A discovered tool of the user's ``integration``, tagged as discovery tags it."""
    item = fake_tool(name)
    item.metadata = {INTEGRATION_KEY: integration}
    return item


def recording_tool(name: str, calls: list[dict[str, Any]], integration: str = "") -> BaseTool:
    """A tool that records its arguments; tagged with ``integration`` like discovery does."""

    def act(**arguments: Any) -> str:
        calls.append(arguments)
        return "sent"

    item = StructuredTool.from_function(
        func=act,
        name=name,
        description="Send an email to a contact.",
        args_schema={"type": "object", "properties": {"to": {"type": "string"}}},
    )
    if integration:
        item.metadata = {INTEGRATION_KEY: integration}
    return item


class ToolThenReport(BaseChatModel):
    """Calls ``tool`` once, then answers with what the tool returned."""

    tool: str
    arguments: dict[str, Any]

    @property
    def _llm_type(self) -> str:
        return "tool-then-report"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        results = [message for message in messages if isinstance(message, ToolMessage)]
        if results:
            reply = AIMessage(content=f"Tool said: {results[-1].text}")
        else:
            call = {"name": self.tool, "args": self.arguments, "id": "call-1"}
            reply = AIMessage(content="", tool_calls=[call])
        return ChatResult(generations=[ChatGeneration(message=reply)])

    def bind_tools(self, tools: Any, **kwargs: Any) -> Runnable[Any, BaseMessage]:
        return self


class AskingAgent:
    """A step agent that asks its step's gate about one tool call and reports the
    answer, so run tests need no model: ``answer-approved`` and so on."""

    def __init__(self, database: Database, limits: ApprovalLimits = FAST_LIMITS) -> None:
        self._database = database
        self._limits = limits
        self.asked_by: list[str] = []

    async def execute(self, task: AgentTask) -> AgentOutcome:
        assert task.run_step is not None, "the graph hands every step of a recorded run its place"
        self.asked_by.append(task.role)
        gate = RunApprovalGate(self._database, task.run_step, self._limits)
        tool = recording_tool("crm_send_email", [])
        status = await gate.ask(ToolRequest(tool, "crm", ARGUMENTS))
        call = ToolCallTrace(tool.name, "success" if status == ApprovalStatus.APPROVED else "error")
        return AgentOutcome(f"answer-{status.value}", [call])
