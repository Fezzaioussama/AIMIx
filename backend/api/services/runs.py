"""Pipeline runs, executed off the request path (AGENTS.md §6).

A run is checked and saved before it starts, then executes on the
``RunExecutor`` while ``RunRecorder`` writes each step as it goes, so clients
poll it, stop it, resume it and find it in their history. Takes and returns
plain Python values — no web-framework objects (§2).

Life of a run: ``queued`` → ``running`` → ``succeeded`` | ``failed`` |
``cancelled`` (stopped by its owner) | ``interrupted`` (the process stopped).
The last three can be resumed: the run continues from its own snapshot,
reusing the steps that succeeded. While a tool call waits for the owner's
approval, a running run is ``waiting`` (``services/approvals``).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from concurrent.futures import CancelledError as FutureCancelledError
from concurrent.futures import Future
from dataclasses import dataclass, field
from functools import partial
from typing import Literal, cast

from api.db import Database
from api.exceptions import Conflict, DomainError, NotFound
from api.models import (
    ACTIVE_RUN_STATUSES,
    RESUMABLE_RUN_STATUSES,
    ApprovalStatus,
    Pipeline,
    Run,
    RunStep,
    StepStatus,
    User,
)
from api.repositories import pipelines as pipeline_repository
from api.repositories import runs as repository
from api.services import run_recorder
from api.services.agent_types import ToolCallTrace
from api.services.approvals import decisions as approvals
from api.services.approvals.decisions import ApprovalAnswer
from api.services.multiagent.contracts import (
    PipelineSpec,
    RunControl,
    RunInputs,
    RunResult,
    StepAgent,
    StepResult,
)
from api.services.multiagent.graph import GraphPipelineRunner, output_orders
from api.services.multiagent.mapper import spec_from_json, spec_to_json
from api.services.pipeline_inputs import bind_run_inputs
from api.services.pipelines import PreparedRun, prepare_run
from api.services.run_executor import RunExecutor
from api.services.run_recorder import RunRecorder

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunStart:
    """What a run is started with: free text, or a value per named input."""

    text: str = ""
    values: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RunOutcome:
    """How one execution ended, for a caller that waits for it. Both fields
    are None when the run was stopped before it began."""

    result: RunResult | None = None
    error: Exception | None = None


@dataclass(frozen=True)
class StartedRun:
    run: Run
    #: Completes when this execution ends; cancelled if the run is stopped.
    finished: Future[RunOutcome]


@dataclass(frozen=True)
class _Plan:
    spec: PipelineSpec
    inputs: RunInputs
    completed: dict[int, StepResult]


def _new_run(pipeline_id: int | None, prepared: PreparedRun, start: RunStart) -> repository.NewRun:
    spec = prepared.spec
    outputs = output_orders(spec.steps)
    return repository.NewRun(
        pipeline_id=pipeline_id,
        pipeline_name=spec.name,
        definition=spec_to_json(spec),
        input_text=start.text,
        input_values=dict(start.values),
        steps=[
            {
                "step_order": step.order,
                "stage": step.stage,
                "title": step.title,
                "model": step.model,
                "is_output": step.order in outputs,
            }
            for step in spec.steps
        ],
    )


def _saved_result(step: RunStep) -> StepResult:
    """A succeeded step as the graph reported it, rebuilt from its row."""
    calls = [
        ToolCallTrace(call["name"], cast(Literal["success", "error"], call["status"]))
        for call in step.tool_calls
    ]
    return StepResult(
        step_order=step.step_order,
        stage=step.stage,
        title=step.title,
        model=step.model,
        input_used=step.input_used,
        output=step.output,
        is_output=step.is_output,
        tool_calls=calls,
    )


def _plan(run: Run) -> _Plan:
    """What an execution needs: the run's own snapshot, its inputs bound again,
    and the steps an earlier attempt finished."""
    spec = spec_from_json(run.pipeline_id, run.definition)
    inputs = bind_run_inputs(spec.inputs, run.input_text, run.input_values)
    done = {
        step.step_order: _saved_result(step)
        for step in run.steps
        if step.status == StepStatus.SUCCEEDED
    }
    return _Plan(spec, inputs, done)


class RunService:
    """Start, stop, resume and delete runs; executions go to the executor."""

    def __init__(self, database: Database, executor: RunExecutor, max_parallel_steps: int) -> None:
        self._database = database
        self._executor = executor
        self._max_parallel_steps = max_parallel_steps

    def start(
        self, user: User, pipeline: Pipeline, start: RunStart, agent: StepAgent
    ) -> StartedRun:
        """Check the inputs (nothing is saved when they are wrong), save the
        run queued, and hand it to the executor."""
        prepared = prepare_run(pipeline, start.text, start.values)
        with self._database.session() as session:
            run = repository.create(session, user, _new_run(pipeline.id, prepared, start))
        finished = self._submit(run.id, agent)
        return StartedRun(self._load(run.id), finished)

    def run_to_end(
        self, user: User, pipeline: Pipeline, start: RunStart, agent: StepAgent
    ) -> RunResult:
        """Start a run and wait for its result; its failure is raised as is."""
        try:
            outcome = self.start(user, pipeline, start, agent).finished.result()
        except FutureCancelledError:
            raise Conflict("The run was stopped before it finished.") from None
        if outcome.error is not None:
            raise outcome.error
        if outcome.result is None:
            raise Conflict("The run was stopped before it started.")
        return outcome.result

    def run_saved_to_end(
        self, user: User, pipeline_id: int, start: RunStart, agent: StepAgent
    ) -> RunResult:
        """``run_to_end`` for one of the user's saved pipelines, by id."""
        with self._database.session() as session:
            pipeline = pipeline_repository.get_owned(session, user, pipeline_id)
        return self.run_to_end(user, pipeline, start, agent)

    def resume(self, user: User, run_id: int, agent: StepAgent) -> Run:
        """Continue a failed, stopped or interrupted run from its first
        unfinished stage. Any other run is returned unchanged."""
        with self._database.session() as session:
            run = repository.get_owned(session, user, run_id)
            if not repository.reopen(session, run.id, RESUMABLE_RUN_STATUSES):
                return run
        logger.info(
            "run.resumed run_id=%s pipeline_id=%s reused_steps=%d",
            run.id,
            run.pipeline_id,
            sum(step.status == StepStatus.SUCCEEDED for step in run.steps),
        )
        self._submit(run.id, agent)
        return self._load(run.id)

    def cancel(self, user: User, run_id: int) -> Run:
        """Stop a queued or running run at once; a finished one is unchanged."""
        with self._database.session() as session:
            run = repository.get_owned(session, user, run_id)
            stopped = repository.end(
                session, run.id, run_recorder.cancelled(), run_recorder.utcnow()
            )
        if stopped:
            self._executor.cancel(run.id)
            logger.info(
                "run.cancelled run_id=%s pipeline_id=%s status=cancelled from=%s",
                run.id,
                run.pipeline_id,
                run.status.value,
            )
            # Stopping expired what the run was waiting on, in one write.
            for asked in run.pending_approvals:
                approvals.log_decided(asked, ApprovalStatus.EXPIRED)
        return self._load(run.id)

    def delete(self, user: User, run_id: int) -> None:
        with self._database.session() as session:
            run = repository.get_owned(session, user, run_id)
            if run.status in ACTIVE_RUN_STATUSES:
                raise Conflict("This run is still in progress. Stop it before deleting it.")
            repository.delete(session, run)

    def answer_approval(self, user: User, given: ApprovalAnswer) -> Run:
        """Approve or decline a tool call the run is waiting on (approval gates);
        the run's step goes on as soon as its gate reads the answer."""
        with self._database.session() as session:
            approvals.answer(session, user, given)
        return self._load(given.run_id)

    def _submit(self, run_id: int, agent: StepAgent) -> Future[RunOutcome]:
        return self._executor.submit(run_id, partial(self._execute, run_id, agent))

    def _load(self, run_id: int) -> Run:
        with self._database.session() as session:
            run = repository.load(session, run_id)
        if run is None:
            raise NotFound(f"Run {run_id} was not found.")
        return run

    async def _execute(self, run_id: int, agent: StepAgent) -> RunOutcome:
        """One execution attempt, on the executor's loop."""
        recorder = RunRecorder(self._database, run_id)
        run = recorder.begin()
        if run is None:
            return RunOutcome()
        runner = GraphPipelineRunner(self._max_parallel_steps)
        try:
            plan = _plan(run)
            control = RunControl(observer=recorder, completed=plan.completed, run_id=run_id)
            result = await runner.arun(plan.spec, agent, plan.inputs, control)
        except asyncio.CancelledError:
            recorder.end(run_recorder.interrupted())
            raise
        except DomainError as error:
            recorder.end(run_recorder.failed(error.code, error.detail))
            return RunOutcome(error=error)
        except Exception as error:
            # The job's boundary, like api/errors._unexpected_error for a request:
            # nobody else would ever see this failure, and the run must not stay
            # "running". Recorded as failed, never as a success.
            logger.exception("run.crashed run_id=%s", run_id)
            recorder.end(
                run_recorder.failed(
                    run_recorder.SERVER_ERROR_CODE, run_recorder.SERVER_ERROR_DETAIL
                )
            )
            return RunOutcome(error=error)
        recorder.end(run_recorder.succeeded(result.final_output))
        return RunOutcome(result=result)


def launcher(
    service: RunService, user: User, agents: Callable[[], StepAgent]
) -> Callable[[int, RunStart], RunResult]:
    """``run_saved_to_end`` bound to one user, for the chat agent's run_pipeline tool."""
    return lambda pipeline_id, start: service.run_saved_to_end(user, pipeline_id, start, agents())


def interrupt_abandoned_runs(database: Database) -> int:
    """At startup: runs a previous process left queued or running can no
    longer finish there, so they become interrupted (and resumable)."""
    with database.session() as session:
        count = repository.interrupt_active(session, run_recorder.utcnow())
    if count:
        logger.warning("run.interrupted_on_startup count=%d", count)
    return count
