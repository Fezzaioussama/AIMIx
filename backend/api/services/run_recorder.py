"""Records a run as it executes: the ``StepObserver`` the graph reports to,
and the run's own start and end.

Each write is a short transaction of its own, so a client polling the run sees
every step as soon as it starts or finishes. Writes run synchronously on the
run's event loop: they take milliseconds on the local database, a run's events
stay in order, and a cancellation can never interrupt one halfway.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timezone
from time import monotonic
from typing import Any

from api.db import Database
from api.models import ACTIVE_RUN_STATUSES, Run, RunStatus, StepStatus
from api.repositories import runs as repository
from api.repositories.runs import RunEnding
from api.services.multiagent.contracts import StepEvent, StepEventKind

logger = logging.getLogger(__name__)

#: Recorded when a run fails for a reason that is not a domain error (a bug).
SERVER_ERROR_CODE = "server_error"
SERVER_ERROR_DETAIL = "An unexpected error occurred."

_RUNNING = frozenset({RunStatus.RUNNING})


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _started(event: StepEvent, now: datetime) -> dict[str, Any]:
    return {"status": StepStatus.RUNNING, "input_used": event.input_used, "started_at": now}


def _succeeded(event: StepEvent, now: datetime) -> dict[str, Any]:
    result = event.result
    assert result is not None  # the graph always attaches it to SUCCEEDED
    return {
        "status": StepStatus.SUCCEEDED,
        "output": result.output,
        "tool_calls": [asdict(call) for call in result.tool_calls],
        "finished_at": now,
    }


def _failed(event: StepEvent, now: datetime) -> dict[str, Any]:
    error = event.error
    return {
        "status": StepStatus.FAILED,
        "error_code": error.code if error else SERVER_ERROR_CODE,
        "error_detail": error.detail if error else SERVER_ERROR_DETAIL,
        "finished_at": now,
    }


def _cancelled(_event: StepEvent, now: datetime) -> dict[str, Any]:
    return {"status": StepStatus.CANCELLED, "finished_at": now}


StepChange = Callable[[StepEvent, datetime], dict[str, Any]]

#: For each event: the step statuses it applies to, and the columns it sets
#: (Strategy + Registry, AGENTS.md §5 O). A step already stopped by the user
#: keeps that status, whatever its agent reports afterwards.
STEP_CHANGES: dict[StepEventKind, tuple[frozenset[StepStatus], StepChange]] = {
    StepEventKind.STARTED: (frozenset({StepStatus.PENDING}), _started),
    StepEventKind.SUCCEEDED: (frozenset({StepStatus.RUNNING}), _succeeded),
    StepEventKind.FAILED: (frozenset({StepStatus.RUNNING}), _failed),
    StepEventKind.CANCELLED: (frozenset({StepStatus.RUNNING}), _cancelled),
}


def succeeded(final_output: str) -> RunEnding:
    return RunEnding(
        RunStatus.SUCCEEDED, _RUNNING, StepStatus.CANCELLED, {"final_output": final_output}
    )


def failed(code: str, detail: str) -> RunEnding:
    """A step's agent or tool failed; a step still marked running crashed with it."""
    return RunEnding(
        RunStatus.FAILED,
        _RUNNING,
        StepStatus.FAILED,
        {"error_code": code, "error_detail": detail},
    )


def interrupted() -> RunEnding:
    """The process stopped the run (shutdown). A run the user stopped first stays cancelled."""
    return RunEnding(RunStatus.INTERRUPTED, _RUNNING, StepStatus.CANCELLED)


def cancelled() -> RunEnding:
    """The user stopped the run, queued or running."""
    return RunEnding(RunStatus.CANCELLED, ACTIVE_RUN_STATUSES, StepStatus.CANCELLED)


class RunRecorder:
    """Writes one run's progress; one recorder per execution attempt."""

    def __init__(self, database: Database, run_id: int) -> None:
        self._database = database
        self._run_id = run_id
        self._pipeline_id: int | None = None
        self._started = monotonic()

    def begin(self) -> Run | None:
        """Mark the queued run running and load it; None when it was stopped
        or deleted while it waited."""
        with self._database.session() as session:
            began = repository.set_status(
                session,
                self._run_id,
                frozenset({RunStatus.QUEUED}),
                {"status": RunStatus.RUNNING, "started_at": utcnow()},
            )
            run = repository.load(session, self._run_id) if began else None
        if run is not None:
            self._pipeline_id = run.pipeline_id
            self._started = monotonic()
            logger.info("run.started run_id=%s pipeline_id=%s", self._run_id, self._pipeline_id)
        return run

    async def on_step_event(self, event: StepEvent) -> None:
        expected, change = STEP_CHANGES[event.kind]
        with self._database.session() as session:
            repository.set_step(
                session, self._run_id, event.step.order, expected, change(event, utcnow())
            )

    def end(self, ending: RunEnding) -> bool:
        """Record how the run ended; False when someone else ended it first."""
        with self._database.session() as session:
            ended = repository.end(session, self._run_id, ending, utcnow())
        if ended:
            logger.info(
                "run.finished run_id=%s pipeline_id=%s status=%s code=%s duration_ms=%.0f",
                self._run_id,
                self._pipeline_id,
                ending.status.value,
                ending.values.get("error_code", ""),
                (monotonic() - self._started) * 1000,
            )
        return ended
