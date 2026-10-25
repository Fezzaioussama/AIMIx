"""Builders shared by the approval-gate tests: runs with requests waiting, a
scripted gate, and a chat model that calls a tool and then reports its result.

Nothing here waits for real: requests expire in fractions of a second.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator, Sequence
from datetime import timedelta
from typing import Any, TypeVar

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool, StructuredTool
from sqlalchemy.orm import Session

from api.db import Database
from api.models import ApprovalStatus, Pipeline, RunApproval, RunStatus, User
from api.repositories import approvals, runs
from api.services.approvals.gate import ToolRequest
from api.services.mcp_discovery import INTEGRATION_KEY
from api.services.run_recorder import utcnow
from api.services.runs import RunService, RunStart
from tests.conftest import FakeProvider

T = TypeVar("T")

#: A request's arguments as the tests send them.
ARGUMENTS = {"to": "ada@example.com", "subject": "Launch"}


class ParkedExecutor:
    """Saves runs without executing them, so a test sets their state by hand."""

    def submit(self, key: int, job: Callable[[], Awaitable[T]]) -> Any:
        from concurrent.futures import Future

        return Future()

    def cancel(self, key: int) -> None:
        return None

    def shutdown(self) -> None:
        return None


def running_run(database: Database, owner: User, pipeline: Pipeline) -> int:
    """A saved run of ``pipeline``, running, as if its job had begun; its id."""
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
        arguments='{"to": "ada@example.com"}',
        arguments_truncated=False,
        created_at=now,
        expires_at=now + expires_in,
    )
    return approvals.ask(session, new)


class ScriptedGate:
    """An ``ApprovalGate`` that answers from a list and remembers what it was asked."""

    def __init__(self, answers: Sequence[ApprovalStatus]) -> None:
        self._answers: Iterator[ApprovalStatus] = iter(answers)
        self.asked: list[ToolRequest] = []

    async def ask(self, request: ToolRequest) -> ApprovalStatus:
        self.asked.append(request)
        return next(self._answers)


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
