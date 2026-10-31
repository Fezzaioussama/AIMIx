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

A run may carry spending limits (``run_budget``): one it does not set takes
the server's default, resuming may raise them, and none may pass the server's
ceiling. Every path that starts or resumes a run goes through ``RunService``,
which applies the server's ``RunPolicy`` there: those limits, how many runs one
account may have active, and how long a caller waiting for a run's end waits.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import CancelledError as FutureCancelledError
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import asdict, dataclass, replace
from functools import partial

from sqlalchemy.orm import Session

from api.db import Database
from api.exceptions import Conflict, DomainError, NotFound, RunStillRunning, TooManyRuns
from api.models import (
    ACTIVE_RUN_STATUSES,
    COMPLETED_STEP_STATUSES,
    RESUMABLE_RUN_STATUSES,
    ApprovalStatus,
    Pipeline,
    Run,
    RunTrigger,
    User,
)
from api.repositories import active_runs
from api.repositories import pipelines as pipeline_repository
from api.repositories import runs as repository
from api.repositories.quota import Quota
from api.services import run_recorder
from api.services.approvals import decisions as approvals
from api.services.approvals.decisions import ApprovalAnswer
from api.services.multiagent.contracts import RunControl, RunResult, StepAgent
from api.services.multiagent.graph import GraphPipelineRunner
from api.services.pipelines import prepare_run
from api.services.run_budget import NO_BUDGET, RunBudget, RunMeter, ensure_room, run_budget
from api.services.run_executor import RunExecutor
from api.services.run_plan import RunStart, new_run, plan_of
from api.services.run_policy import RunPolicy, run_policy
from api.services.run_recorder import RunRecorder
from api.services.usage import total_usage
from config.settings import get_settings

logger = logging.getLogger(__name__)


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


class RunService:
    """Start, stop, resume and delete runs; executions go to the executor."""

    def __init__(
        self,
        database: Database,
        executor: RunExecutor,
        max_parallel_steps: int,
        policy: RunPolicy | None = None,
    ) -> None:
        self._database = database
        self._executor = executor
        self._max_parallel_steps = max_parallel_steps
        #: None reads it from the settings (RUN_DEFAULT_MAX_*, RUN_MAX_*, ...).
        self._policy = policy if policy is not None else run_policy(get_settings())

    def start(
        self, user: User, pipeline: Pipeline, start: RunStart, agent: StepAgent
    ) -> StartedRun:
        """Check the inputs and limits (nothing is saved when they are wrong),
        save the run queued with its limits, as long as its owner has room for
        one more active run, and hand it to the executor."""
        prepared = prepare_run(pipeline, start.text, start.values)
        limits = self._policy.limits
        limited = replace(start, budget=limits.applied(limits.allow(start.budget)))
        self._ensure_disk_room()
        with self._database.session() as session:
            row = new_run(pipeline.id, prepared, limited)
            run = repository.create(session, user, row, self._active_cap())
        finished = self._submit(run.id, agent)
        return StartedRun(self._load(run.id), finished)

    def run_to_end(
        self, user: User, pipeline: Pipeline, start: RunStart, agent: StepAgent
    ) -> RunResult:
        """Start a run and wait for its result, at most RUN_WAIT_MAX_SECONDS
        (then ``RunStillRunning``: it goes on); its failure is raised as is."""
        started = self.start(user, pipeline, start, agent)
        wait = self._policy.wait_seconds
        try:
            outcome = started.finished.result(timeout=wait)
        except FutureTimeoutError:
            raise RunStillRunning(started.run.id, wait or 0.0) from None
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

    def resume(
        self, user: User, run_id: int, agent: StepAgent, budget: RunBudget = NO_BUDGET
    ) -> Run:
        """Continue a failed, stopped or interrupted run from its first
        unfinished stage, with ``budget``'s limits in place of the run's own
        (one left unset stays). Any other run is returned unchanged; a run that
        would still be over a limit is refused with ``BudgetExceeded``, and one
        whose last attempt is still winding down with ``Conflict``."""
        with self._database.session() as session:
            run = repository.get_owned(session, user, run_id)
            if not self._reopen(session, run, budget):
                return run
        logger.info(
            "run.resumed run_id=%s pipeline_id=%s reused_steps=%d",
            run.id,
            run.pipeline_id,
            sum(step.status in COMPLETED_STEP_STATUSES for step in run.steps),
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

    def _reopen(self, session: Session, run: Run, budget: RunBudget) -> bool:
        """Queue a resumable run again under ``budget``'s limits (the run's own,
        then the default, where it sets none); False for a run that is not resumable."""
        if run.status not in RESUMABLE_RUN_STATUSES:
            return False
        if not self._executor.settled(run.id):
            # Its stopped attempt has not ended yet, and would record its end on the next one.
            raise Conflict("This run is still stopping. Try again in a moment.")
        limits = self._policy.limits
        chosen = limits.applied(limits.allow(budget), run_budget(run))
        ensure_room(chosen, total_usage(run.steps))
        self._ensure_disk_room()
        return repository.reopen(session, run, asdict(chosen), self._active_cap())

    def _ensure_disk_room(self) -> None:
        """A run grows the database: none starts or resumes past the disk reserve."""
        if self._policy.disk is not None:
            self._policy.disk.ensure_room()

    def _active_cap(self) -> Quota | None:
        """RUN_MAX_ACTIVE_PER_USER, as the quota a start or a resume must fit in."""
        cap = self._policy.max_active_per_user
        return None if cap is None else Quota(cap, TooManyRuns(cap))

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
            plan = plan_of(run)
            meter = RunMeter(plan.budget, plan.spent, recorder.record_usage)
            control = RunControl(
                observer=recorder,
                completed=plan.completed,
                meter=meter.for_step,
                run_id=run_id,
                rounds=plan.rounds,
            )
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
    """``run_saved_to_end`` bound to one user, for the chat agent's run_pipeline
    tool; its runs are marked as started from chat."""
    return lambda pipeline_id, start: service.run_saved_to_end(
        user, pipeline_id, replace(start, trigger=RunTrigger.CHAT), agents()
    )


def interrupt_abandoned_runs(database: Database) -> int:
    """At startup: runs a previous process left queued or running can no
    longer finish there, so they become interrupted (and resumable)."""
    with database.session() as session:
        count = active_runs.interrupt_active(session, run_recorder.utcnow())
    if count:
        logger.warning("run.interrupted_on_startup count=%d", count)
    return count
