"""Background runs end to end: the real executor, a file database (one
connection per thread) and fake step agents."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable, Iterator
from concurrent.futures import CancelledError as FutureCancelledError
from concurrent.futures import Future
from pathlib import Path
from typing import TypeVar

import pytest

from api.db import Database
from api.exceptions import Conflict, ProviderUnavailable, ValidationFailed
from api.models import Base, Pipeline, Run, RunStatus, StepStatus, User
from api.repositories import pipelines, runs, users
from api.repositories.pipelines import PipelineChanges
from api.repositories.runs import StepChange
from api.services.agent_types import AgentOutcome, AgentTask, ToolCallTrace
from api.services.run_executor import BackgroundRunExecutor
from api.services.runs import RunService, RunStart, interrupt_abandoned_runs

WAIT_SECONDS = 5.0
T = TypeVar("T")


class ScriptedAgent:
    """Answers ``out-<role>``; ``fail`` roles raise once each, ``hold`` roles
    wait until ``release`` is set (or the run is stopped)."""

    def __init__(self, fail: tuple[str, ...] = (), hold: tuple[str, ...] = ()) -> None:
        self.fail = set(fail)
        self.hold = set(hold)
        self.release = threading.Event()
        self.prompts: dict[str, str] = {}
        self.calls: list[str] = []
        self.cancelled: list[str] = []

    async def execute(self, task: AgentTask) -> AgentOutcome:
        self.calls.append(task.role)
        self.prompts[task.role] = task.prompt
        if task.role in self.hold:
            await self._held(task.role)
        if task.role in self.fail:
            self.fail.discard(task.role)
            raise ProviderUnavailable(f"{task.role} failed")
        return AgentOutcome(f"out-{task.role}", [ToolCallTrace("calculator", "success")])

    async def _held(self, role: str) -> None:
        try:
            while not self.release.is_set():
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            self.cancelled.append(role)
            raise


class CrashingAgent:
    async def execute(self, task: AgentTask) -> AgentOutcome:
        raise RuntimeError("a bug")


class ParkedExecutor:
    """A process that saves runs and then disappears before executing them."""

    def submit(self, key: int, job: Callable[[], Awaitable[T]]) -> Future[T]:
        return Future()

    def cancel(self, key: int) -> None:
        return None

    def settled(self, key: int) -> bool:
        return True

    def shutdown(self) -> None:
        return None


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db = Database(f"sqlite:///{tmp_path / 'runs.sqlite3'}")
    Base.metadata.create_all(db.engine)
    yield db
    db.engine.dispose()


@pytest.fixture
def owner(database: Database) -> User:
    with database.session() as session:
        return users.create(session, "runner", "hash")


@pytest.fixture
def executor() -> Iterator[BackgroundRunExecutor]:
    background = BackgroundRunExecutor(max_concurrent=2, grace_seconds=2.0)
    yield background
    background.shutdown()


@pytest.fixture
def service(database: Database, executor: BackgroundRunExecutor) -> RunService:
    return RunService(database, executor, max_parallel_steps=4)


def make_pipeline(database: Database, owner: User, stages: list[int]) -> Pipeline:
    """Step ``n`` (from 1) has role ``role-n`` and runs in ``stages[n - 1]``."""
    steps = [
        {"order": n, "stage": stage, "prompt": f"p{n} {{input}}", "model": "m", "role": f"role-{n}"}
        for n, stage in enumerate(stages, start=1)
    ]
    with database.session() as session:
        return pipelines.create_with_steps(session, owner, PipelineChanges("Flow", steps=steps))


def load(database: Database, run_id: int) -> Run:
    with database.session() as session:
        run = runs.load(session, run_id)
    assert run is not None
    return run


def wait_for(database: Database, run_id: int, done: Callable[[Run], bool]) -> Run:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        run = load(database, run_id)
        if done(run):
            return run
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} never got there: {load(database, run_id).status}")


def statuses(run: Run) -> list[StepStatus]:
    return [step.status for step in run.steps]


def test_a_run_executes_in_the_background_and_records_every_step(
    database: Database, owner: User, service: RunService
) -> None:
    pipeline = make_pipeline(database, owner, [1, 1, 2])

    started = service.start(owner, pipeline, RunStart("seed"), ScriptedAgent())
    outcome = started.finished.result(timeout=WAIT_SECONDS)

    assert started.run.status in (RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.SUCCEEDED)
    assert outcome.result is not None and outcome.result.final_output == "out-role-3"
    run = load(database, started.run.id)
    assert run.status == RunStatus.SUCCEEDED
    assert run.final_output == "out-role-3"
    assert run.started_at is not None and run.finished_at is not None
    assert statuses(run) == [StepStatus.SUCCEEDED] * 3
    assert [step.output for step in run.steps] == ["out-role-1", "out-role-2", "out-role-3"]
    assert run.steps[0].input_used == "seed"
    assert run.steps[0].tool_calls == [{"name": "calculator", "status": "success"}]
    assert [step.is_output for step in run.steps] == [False, False, True]
    assert all(step.finished_at is not None for step in run.steps)


def test_inputs_are_checked_before_anything_is_saved(
    database: Database, owner: User, service: RunService
) -> None:
    pipeline = make_pipeline(database, owner, [1])

    with pytest.raises(ValidationFailed, match="must not be blank"):
        service.start(owner, pipeline, RunStart("   "), ScriptedAgent())

    with database.session() as session:
        assert session.query(Run).count() == 0


def test_a_failing_step_fails_the_run_and_stops_its_parallel_sibling(
    database: Database, owner: User, service: RunService
) -> None:
    pipeline = make_pipeline(database, owner, [1, 1, 2])
    agent = ScriptedAgent(fail=("role-1",), hold=("role-2",))

    started = service.start(owner, pipeline, RunStart("seed"), agent)
    outcome = started.finished.result(timeout=WAIT_SECONDS)

    assert isinstance(outcome.error, ProviderUnavailable)
    run = load(database, started.run.id)
    assert (run.status, run.error_code) == (RunStatus.FAILED, "provider_unavailable")
    assert statuses(run) == [StepStatus.FAILED, StepStatus.CANCELLED, StepStatus.PENDING]
    assert run.steps[0].error_detail == "role-1 failed"
    assert agent.cancelled == ["role-2"]


def test_an_unexpected_error_fails_the_run_without_leaving_it_running(
    database: Database, owner: User, service: RunService
) -> None:
    pipeline = make_pipeline(database, owner, [1])

    started = service.start(owner, pipeline, RunStart("seed"), CrashingAgent())
    outcome = started.finished.result(timeout=WAIT_SECONDS)

    assert isinstance(outcome.error, RuntimeError)
    run = load(database, started.run.id)
    assert (run.status, run.error_code) == (RunStatus.FAILED, "server_error")
    assert statuses(run) == [StepStatus.FAILED]


def test_stopping_a_running_run_cancels_its_step_at_once(
    database: Database, owner: User, service: RunService
) -> None:
    pipeline = make_pipeline(database, owner, [1, 2])
    agent = ScriptedAgent(hold=("role-1",))
    started = service.start(owner, pipeline, RunStart("seed"), agent)
    wait_for(database, started.run.id, lambda run: run.steps[0].status == StepStatus.RUNNING)

    stopped = service.cancel(owner, started.run.id)

    assert stopped.status == RunStatus.CANCELLED
    assert statuses(stopped) == [StepStatus.CANCELLED, StepStatus.PENDING]
    with pytest.raises(FutureCancelledError):
        started.finished.result(timeout=WAIT_SECONDS)
    assert agent.cancelled == ["role-1"]
    # Stopping again is harmless, and the executor's own wind-down kept "cancelled".
    assert service.cancel(owner, started.run.id).status == RunStatus.CANCELLED
    assert load(database, started.run.id).status == RunStatus.CANCELLED
    assert agent.calls == ["role-1"]


def test_runs_beyond_the_limit_wait_queued_and_can_be_stopped_there(
    database: Database, owner: User
) -> None:
    single = BackgroundRunExecutor(max_concurrent=1, grace_seconds=2.0)
    service = RunService(database, single, max_parallel_steps=4)
    pipeline = make_pipeline(database, owner, [1])
    first_agent, second_agent, third_agent = (
        ScriptedAgent(hold=("role-1",)),
        ScriptedAgent(),
        ScriptedAgent(),
    )
    try:
        first = service.start(owner, pipeline, RunStart("one"), first_agent)
        wait_for(database, first.run.id, lambda run: run.status == RunStatus.RUNNING)
        second = service.start(owner, pipeline, RunStart("two"), second_agent)
        third = service.start(owner, pipeline, RunStart("three"), third_agent)
        time.sleep(0.1)
        assert load(database, second.run.id).status == RunStatus.QUEUED

        assert service.cancel(owner, second.run.id).status == RunStatus.CANCELLED
        first_agent.release.set()

        assert third.finished.result(timeout=WAIT_SECONDS).result is not None
        assert load(database, first.run.id).status == RunStatus.SUCCEEDED
        assert load(database, second.run.id).status == RunStatus.CANCELLED
        assert second_agent.calls == []
    finally:
        first_agent.release.set()
        single.shutdown()


def test_resuming_a_failed_run_reuses_the_steps_that_succeeded(
    database: Database, owner: User, service: RunService
) -> None:
    pipeline = make_pipeline(database, owner, [1, 2, 3])
    first_try = ScriptedAgent(fail=("role-2",))
    started = service.start(owner, pipeline, RunStart("seed"), first_try)
    started.finished.result(timeout=WAIT_SECONDS)
    # Editing the pipeline afterwards does not change what the run executes.
    with database.session() as session:
        saved = pipelines.get_owned(session, owner, pipeline.id)
        steps = [
            {"order": n, "stage": n, "prompt": "edited", "model": "m", "role": f"role-{n}"}
            for n in (1, 2, 3)
        ]
        pipelines.replace_steps(session, saved, PipelineChanges(steps=steps))

    second_try = ScriptedAgent()
    resumed = service.resume(owner, started.run.id, second_try)
    assert resumed.status in (RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.SUCCEEDED)
    run = wait_for(database, started.run.id, lambda run: run.status == RunStatus.SUCCEEDED)

    assert first_try.calls == ["role-1", "role-2"]
    assert second_try.calls == ["role-2", "role-3"]
    assert second_try.prompts["role-2"] == "p2 out-role-1"
    assert statuses(run) == [StepStatus.SUCCEEDED] * 3
    assert (run.final_output, run.error_code) == ("out-role-3", "")


def test_resuming_a_run_with_nothing_left_to_do_changes_nothing(
    database: Database, owner: User, service: RunService
) -> None:
    pipeline = make_pipeline(database, owner, [1])
    started = service.start(owner, pipeline, RunStart("seed"), ScriptedAgent())
    started.finished.result(timeout=WAIT_SECONDS)
    agent = ScriptedAgent()

    assert service.resume(owner, started.run.id, agent).status == RunStatus.SUCCEEDED
    time.sleep(0.05)
    assert agent.calls == []


def test_runs_a_stopped_process_left_active_become_interrupted_and_resumable(
    database: Database, owner: User, service: RunService
) -> None:
    pipeline = make_pipeline(database, owner, [1, 2])
    # The previous process saved two runs, then died: one queued, one mid-way.
    previous = RunService(database, ParkedExecutor(), max_parallel_steps=4)
    queued = previous.start(owner, pipeline, RunStart("one"), ScriptedAgent()).run
    midway = previous.start(owner, pipeline, RunStart("two"), ScriptedAgent()).run
    pending = frozenset({StepStatus.PENDING})
    with database.session() as session:
        runs.set_status(session, midway.id, [RunStatus.QUEUED], {"status": RunStatus.RUNNING})
        done = {"status": StepStatus.SUCCEEDED, "input_used": "two", "output": "kept"}
        runs.set_step(session, midway.id, StepChange(1, pending, done))
        runs.set_step(session, midway.id, StepChange(2, pending, {"status": StepStatus.RUNNING}))

    assert interrupt_abandoned_runs(database) == 2

    assert load(database, queued.id).status == RunStatus.INTERRUPTED
    run = load(database, midway.id)
    assert run.status == RunStatus.INTERRUPTED
    assert statuses(run) == [StepStatus.SUCCEEDED, StepStatus.CANCELLED]
    agent = ScriptedAgent()
    service.resume(owner, run.id, agent)
    resumed = wait_for(database, run.id, lambda again: again.status == RunStatus.SUCCEEDED)
    assert agent.calls == ["role-2"]
    assert agent.prompts["role-2"] == "p2 kept"
    assert resumed.steps[0].output == "kept"


def test_shutting_down_interrupts_active_runs_instead_of_cancelling_them(
    database: Database, owner: User, executor: BackgroundRunExecutor, service: RunService
) -> None:
    pipeline = make_pipeline(database, owner, [1])
    agent = ScriptedAgent(hold=("role-1",))
    started = service.start(owner, pipeline, RunStart("seed"), agent)
    wait_for(database, started.run.id, lambda run: run.status == RunStatus.RUNNING)

    executor.shutdown()

    run = load(database, started.run.id)
    assert run.status == RunStatus.INTERRUPTED
    assert statuses(run) == [StepStatus.CANCELLED]


def test_an_active_run_cannot_be_deleted_but_a_finished_one_can(
    database: Database, owner: User, service: RunService
) -> None:
    pipeline = make_pipeline(database, owner, [1])
    agent = ScriptedAgent(hold=("role-1",))
    started = service.start(owner, pipeline, RunStart("seed"), agent)

    with pytest.raises(Conflict):
        service.delete(owner, started.run.id)

    agent.release.set()
    started.finished.result(timeout=WAIT_SECONDS)
    service.delete(owner, started.run.id)
    with database.session() as session:
        assert runs.load(session, started.run.id) is None
