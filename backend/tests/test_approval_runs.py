"""A run that asks before acting, end to end: the real background executor, a
file database and step agents that stop at the approval gate."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import CancelledError as FutureCancelledError
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.db import Database
from api.deps import pipeline_agent_factory
from api.exceptions import ProviderUnavailable
from api.main import create_app
from api.models import ApprovalStatus, Base, Pipeline, Run, RunApproval, RunStatus, StepStatus, User
from api.repositories import approvals, runs
from api.repositories.runs import StepChange
from api.services.agent_types import AgentOutcome, AgentTask
from api.services.approvals.decisions import ApprovalAnswer
from api.services.multiagent.contracts import StepAgent
from api.services.run_executor import BackgroundRunExecutor
from api.services.runs import RunService, RunStart, interrupt_abandoned_runs
from config.settings import pin_settings
from tests.approval_fakes import (
    FAST_LIMITS,
    AskingAgent,
    approval_status,
    file_database,
    make_owner,
    make_pipeline,
    request_approval,
    run_status,
    running_run,
)
from tests.conftest import TEST_SETTINGS, bearer
from tests.test_runs_service import WAIT_SECONDS, load, statuses, wait_for


class RoleAgents:
    """Hands each step to the agent registered for its role."""

    def __init__(self, **agents: StepAgent) -> None:
        self._agents = agents

    async def execute(self, task: AgentTask) -> AgentOutcome:
        return await self._agents[task.role.replace("-", "_")].execute(task)


class FailsOnRelease:
    """Holds its step until released, then fails it."""

    def __init__(self) -> None:
        self.release = threading.Event()

    async def execute(self, task: AgentTask) -> AgentOutcome:
        while not self.release.is_set():
            await asyncio.sleep(0.01)
        raise ProviderUnavailable("this step failed")


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db = file_database(tmp_path)
    yield db
    db.engine.dispose()


@pytest.fixture
def owner(database: Database) -> User:
    return make_owner(database)


@pytest.fixture
def executor() -> Iterator[BackgroundRunExecutor]:
    background = BackgroundRunExecutor(max_concurrent=2, grace_seconds=2.0)
    yield background
    background.shutdown()


@pytest.fixture
def service(database: Database, executor: BackgroundRunExecutor) -> RunService:
    return RunService(database, executor, max_parallel_steps=4)


def pending(run: Run, count: int = 1) -> bool:
    return len(run.pending_approvals) == count


def waiting_for(database: Database, run_id: int, count: int = 1) -> Run:
    """The run once its agents have asked ``count`` times and nobody answered."""
    return wait_for(
        database, run_id, lambda run: run.status == RunStatus.WAITING and pending(run, count)
    )


def answer(service: RunService, owner: User, approval: RunApproval, status: ApprovalStatus) -> None:
    service.answer_approval(owner, ApprovalAnswer(approval.run_id, approval.id, status))


def test_a_run_waits_for_its_owner_and_goes_on_once_approved(
    database: Database, owner: User, service: RunService
) -> None:
    started = service.start(
        owner, make_pipeline(database, owner), RunStart("go"), AskingAgent(database)
    )

    run = waiting_for(database, started.run.id)

    assert statuses(run) == [StepStatus.RUNNING]
    [asked] = run.pending_approvals
    assert asked.tool_name == "crm_send_email" and asked.step_order == 1
    answer(service, owner, asked, ApprovalStatus.APPROVED)
    outcome = started.finished.result(timeout=WAIT_SECONDS)
    assert outcome.result is not None and outcome.result.final_output == "answer-approved"
    done = load(database, started.run.id)
    assert (done.status, done.pending_approvals) == (RunStatus.SUCCEEDED, [])
    assert done.steps[0].tool_calls == [{"name": "crm_send_email", "status": "success"}]
    assert approval_status(database, asked.id) == ApprovalStatus.APPROVED


def test_a_declined_call_reaches_the_agent_and_the_run_finishes_anyway(
    database: Database, owner: User, service: RunService
) -> None:
    started = service.start(
        owner, make_pipeline(database, owner), RunStart("go"), AskingAgent(database)
    )
    [asked] = waiting_for(database, started.run.id).pending_approvals

    answer(service, owner, asked, ApprovalStatus.DECLINED)

    assert started.finished.result(timeout=WAIT_SECONDS).result is not None
    done = load(database, started.run.id)
    assert (done.status, done.final_output) == (RunStatus.SUCCEEDED, "answer-declined")
    assert done.steps[0].tool_calls == [{"name": "crm_send_email", "status": "error"}]
    assert approval_status(database, asked.id) == ApprovalStatus.DECLINED


def test_an_unanswered_request_expires_and_the_run_goes_on(
    database: Database, owner: User, service: RunService
) -> None:
    impatient = AskingAgent(database, replace(FAST_LIMITS, timeout_seconds=0.1))

    started = service.start(owner, make_pipeline(database, owner), RunStart("go"), impatient)

    assert started.finished.result(timeout=WAIT_SECONDS).result is not None
    done = load(database, started.run.id)
    assert (done.status, done.final_output) == (RunStatus.SUCCEEDED, "answer-expired")
    assert done.pending_approvals == []


def test_stopping_a_waiting_run_expires_its_request_and_cancels_its_step(
    database: Database, owner: User, service: RunService
) -> None:
    agent = AskingAgent(database)
    started = service.start(owner, make_pipeline(database, owner, [1, 2]), RunStart("go"), agent)
    [asked] = waiting_for(database, started.run.id).pending_approvals

    stopped = service.cancel(owner, started.run.id)

    assert stopped.status == RunStatus.CANCELLED
    assert statuses(stopped) == [StepStatus.CANCELLED, StepStatus.PENDING]
    assert stopped.pending_approvals == []
    with pytest.raises(FutureCancelledError):
        started.finished.result(timeout=WAIT_SECONDS)
    assert approval_status(database, asked.id) == ApprovalStatus.EXPIRED
    assert agent.asked_by == ["role-1"]
    assert run_status(database, started.run.id) == RunStatus.CANCELLED


def test_shutting_down_interrupts_a_waiting_run_and_expires_its_request(
    database: Database, owner: User, executor: BackgroundRunExecutor, service: RunService
) -> None:
    started = service.start(
        owner, make_pipeline(database, owner), RunStart("go"), AskingAgent(database)
    )
    [asked] = waiting_for(database, started.run.id).pending_approvals

    executor.shutdown()

    run = load(database, started.run.id)
    assert (run.status, statuses(run)) == (RunStatus.INTERRUPTED, [StepStatus.CANCELLED])
    assert approval_status(database, asked.id) == ApprovalStatus.EXPIRED


def test_a_crash_leaves_a_waiting_run_interrupted_and_resuming_it_asks_again(
    database: Database, owner: User, service: RunService
) -> None:
    run_id = running_run(database, owner, make_pipeline(database, owner))
    with database.session() as session:
        first = request_approval(session, run_id)
        running = {"status": StepStatus.RUNNING}
        runs.set_step(session, run_id, StepChange(1, frozenset({StepStatus.PENDING}), running))
    assert run_status(database, run_id) == RunStatus.WAITING

    assert interrupt_abandoned_runs(database) == 1

    interrupted = load(database, run_id)
    assert (interrupted.status, statuses(interrupted)) == (
        RunStatus.INTERRUPTED,
        [StepStatus.CANCELLED],
    )
    assert interrupted.pending_approvals == []
    assert approval_status(database, first.id) == ApprovalStatus.EXPIRED
    service.resume(owner, run_id, AskingAgent(database))
    [again] = waiting_for(database, run_id).pending_approvals
    assert again.id != first.id
    answer(service, owner, again, ApprovalStatus.APPROVED)
    done = wait_for(database, run_id, lambda run: run.status == RunStatus.SUCCEEDED)
    assert done.final_output == "answer-approved"


def test_parallel_steps_ask_separately_and_the_run_waits_for_every_answer(
    database: Database, owner: User, service: RunService
) -> None:
    started = service.start(
        owner, make_pipeline(database, owner, [1, 1]), RunStart("go"), AskingAgent(database)
    )
    first, second = waiting_for(database, started.run.id, count=2).pending_approvals

    answer(service, owner, first, ApprovalStatus.APPROVED)

    assert run_status(database, started.run.id) == RunStatus.WAITING
    answer(service, owner, second, ApprovalStatus.DECLINED)
    done = wait_for(database, started.run.id, lambda run: run.status == RunStatus.SUCCEEDED)
    assert done.pending_approvals == []
    assert approval_status(database, first.id) == ApprovalStatus.APPROVED
    assert approval_status(database, second.id) == ApprovalStatus.DECLINED


def test_a_failing_step_expires_what_its_parallel_sibling_was_asking(
    database: Database, owner: User, service: RunService
) -> None:
    failing = FailsOnRelease()
    agents = RoleAgents(role_1=failing, role_2=AskingAgent(database))
    started = service.start(owner, make_pipeline(database, owner, [1, 1]), RunStart("go"), agents)
    [asked] = waiting_for(database, started.run.id).pending_approvals

    failing.release.set()

    outcome = started.finished.result(timeout=WAIT_SECONDS)
    assert isinstance(outcome.error, ProviderUnavailable)
    run = load(database, started.run.id)
    assert (run.status, run.error_code) == (RunStatus.FAILED, "provider_unavailable")
    assert statuses(run) == [StepStatus.FAILED, StepStatus.CANCELLED]
    assert run.pending_approvals == []
    assert approval_status(database, asked.id) == ApprovalStatus.EXPIRED


def test_a_request_is_not_taken_back_once_it_is_answered(
    database: Database, owner: User, service: RunService
) -> None:
    started = service.start(
        owner, make_pipeline(database, owner), RunStart("go"), AskingAgent(database)
    )
    [asked] = waiting_for(database, started.run.id).pending_approvals
    answer(service, owner, asked, ApprovalStatus.APPROVED)
    started.finished.result(timeout=WAIT_SECONDS)

    with database.session() as session:
        late = approvals.settle(
            session,
            approvals.Settlement(asked.run_id, asked.id, ApprovalStatus.EXPIRED, asked.created_at),
        )

    assert late is False
    assert approval_status(database, asked.id) == ApprovalStatus.APPROVED


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[TestClient, Pipeline]]:
    """The whole app on a file database, its runs on the real executor, its step
    agents stopping at the gate."""
    pin_settings(
        TEST_SETTINGS.model_copy(update={"database_url": f"sqlite:///{tmp_path / 'app.sqlite3'}"})
    )
    try:
        app = create_app()
        Base.metadata.create_all(app.state.database.engine)
        mine = make_owner(app.state.database, "http-owner")
        pipeline = make_pipeline(app.state.database, mine)
        agent = AskingAgent(app.state.database)
        app.dependency_overrides[pipeline_agent_factory] = lambda: lambda: agent
        with TestClient(app) as client:
            client.headers.update(bearer(mine))
            yield client, pipeline
    finally:
        pin_settings(TEST_SETTINGS)


@pytest.mark.parametrize(
    ("answer_to_give", "reported"), [("approve", "answer-approved"), ("decline", "answer-declined")]
)
def test_the_whole_flow_over_http(
    served: tuple[TestClient, Pipeline], answer_to_give: str, reported: str
) -> None:
    client, pipeline = served
    run_id = client.post(f"/api/pipelines/{pipeline.id}/runs", json={"input": "go"}).json()["id"]

    waiting = poll(client, run_id, lambda body: body["status"] == "waiting")
    [asked] = waiting["pending_approvals"]
    answered = client.post(f"/api/runs/{run_id}/approvals/{asked['id']}/{answer_to_give}")

    assert answered.status_code == 200
    done = poll(client, run_id, lambda body: body["status"] == "succeeded")
    assert done["final_output"] == reported
    assert done["pending_approvals"] == []
    waiting_list = client.get("/api/runs", params={"status": "waiting"}).json()
    assert waiting_list == {"items": [], "total": 0}


def poll(client: TestClient, run_id: int, done: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    """The run as the API shows it, once ``done`` says so."""
    deadline = time.monotonic() + WAIT_SECONDS
    body: dict[str, Any] = {}
    while time.monotonic() < deadline:
        body = client.get(f"/api/runs/{run_id}").json()
        if done(body):
            return body
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} never got there: {body.get('status')}")
