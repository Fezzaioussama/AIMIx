"""What the recorded-run tests of conditions and review loops share: a pipeline
saved in one line, the usual research -> writer -> reviewer team, and readers
for the rows a run leaves behind."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from api.db import Database
from api.models import Pipeline, Run, RunStep, StepStatus, User
from api.repositories import pipelines, runs
from api.repositories.pipelines import PipelineChanges
from tests.flow.fakes import stored_step

WAIT_SECONDS = 5.0


def save_pipeline(
    database: Database,
    owner: User,
    *steps: dict[str, Any],
    inputs: list[dict[str, str]] | None = None,
) -> Pipeline:
    with database.session() as session:
        changes = PipelineChanges("Flow", inputs=inputs or [], steps=list(steps))
        return pipelines.create_with_steps(session, owner, changes)


def review_team(
    database: Database, owner: User, max_rounds: int = 2, publisher: bool = False
) -> Pipeline:
    """research (stage 1) -> writer (2) -> reviewer (3, sends work back to 2), and
    optionally a publisher (4) after the loop."""
    steps = [
        stored_step(1, 1, "research"),
        stored_step(2, 2, "writer"),
        stored_step(3, 3, "reviewer", review={"send_back_to_stage": 2, "max_rounds": max_rounds}),
    ]
    if publisher:
        steps.append(stored_step(4, 4, "publisher"))
    return save_pipeline(database, owner, *steps)


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


def row(run: Run, order: int) -> RunStep:
    return next(step for step in run.steps if step.step_order == order)


def statuses(run: Run) -> list[StepStatus]:
    return [step.status for step in run.steps]


def rounds(run: Run) -> list[int]:
    return [step.rounds for step in run.steps]
