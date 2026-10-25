"""What the recorder writes for each step event, and from which step statuses.

Every write is a compare-and-set: only a review loop's redo takes a finished
step back to running, and a step the owner stopped keeps that status."""

from __future__ import annotations

import asyncio

from api.db import Database
from api.models import RunStatus, RunStep, StepStatus, User
from api.repositories import runs
from api.repositories.runs import StepChange
from api.services.multiagent.contracts import StepEvent, StepEventKind, StepResult
from api.services.multiagent.reviews import Verdict
from api.services.run_recorder import RunRecorder
from api.services.runs import RunService, RunStart
from tests.approval_fakes import ParkedExecutor
from tests.flow.fakes import ScriptedAgent, step
from tests.flow.support import load, review_team, row

SPEC = step(2, 2, "writer")
STARTED, AGAIN = StepEventKind.STARTED, StepEventKind.RESTARTED
SKIPPED, DONE = StepEventKind.SKIPPED, StepEventKind.SUCCEEDED
FAILED, CANCELLED = StepEventKind.FAILED, StepEventKind.CANCELLED


def saved_run(database: Database, owner: User) -> int:
    """A queued run of the research -> writer -> reviewer team; its id."""
    parked = RunService(database, ParkedExecutor(), max_parallel_steps=4)
    run = parked.start(owner, review_team(database, owner), RunStart("seed"), ScriptedAgent()).run
    with database.session() as session:
        runs.set_status(session, run.id, [RunStatus.QUEUED], {"status": RunStatus.RUNNING})
    return run.id


def put(database: Database, run_id: int, **values: object) -> None:
    """Set the writer's row, whatever state it is in."""
    with database.session() as session:
        change = StepChange(2, frozenset(StepStatus), values)
        assert runs.set_step(session, run_id, change)


def send(database: Database, run_id: int, event: StepEvent) -> RunStep:
    asyncio.run(RunRecorder(database, run_id).on_step_event(event))
    return row(load(database, run_id), 2)


def event(kind: StepEventKind, round_: int = 1, result: StepResult | None = None) -> StepEvent:
    return StepEvent(kind, SPEC, "the input", result=result, round=round_)


def finished_result(round_: int = 2, verdict: Verdict | None = None) -> StepResult:
    return StepResult(2, 2, "Writer", "m", "the input", "new draft", rounds=round_, verdict=verdict)


def test_a_first_start_takes_a_pending_step_and_records_its_round(
    database: Database, owner: User
) -> None:
    run_id = saved_run(database, owner)

    started = send(database, run_id, event(STARTED, round_=3))

    assert (started.status, started.rounds, started.input_used) == (
        StepStatus.RUNNING,
        3,
        "the input",
    )
    assert started.started_at is not None


def test_a_plain_start_does_not_reopen_a_finished_step(database: Database, owner: User) -> None:
    run_id = saved_run(database, owner)
    put(database, run_id, status=StepStatus.SUCCEEDED, output="done")

    untouched = send(database, run_id, event(STARTED))

    assert (untouched.status, untouched.output) == (StepStatus.SUCCEEDED, "done")


def test_a_restart_takes_a_finished_step_back_to_running_and_clears_its_result(
    database: Database, owner: User
) -> None:
    run_id = saved_run(database, owner)
    put(
        database,
        run_id,
        status=StepStatus.SUCCEEDED,
        output="old draft",
        verdict="revise",
        tool_calls=[{"name": "calculator", "status": "success"}],
        error_code="x",
        error_detail="y",
        input_tokens=120,
        output_tokens=30,
        cost_usd=0.5,
        finished_at=None,
    )

    again = send(database, run_id, event(AGAIN, round_=2))

    assert (again.status, again.rounds) == (StepStatus.RUNNING, 2)
    assert (again.output, again.verdict, again.tool_calls) == ("", None, [])
    assert (again.error_code, again.error_detail, again.finished_at) == ("", "", None)
    # What the first round spent stays: the next round's calls add to it.
    assert (again.input_tokens, again.output_tokens, again.cost_usd) == (120, 30, 0.5)


def test_a_restart_also_takes_a_skipped_step_but_not_one_that_never_finished(
    database: Database, owner: User
) -> None:
    run_id = saved_run(database, owner)
    put(database, run_id, status=StepStatus.SKIPPED)
    assert send(database, run_id, event(AGAIN, 2)).status == StepStatus.RUNNING

    for status in (StepStatus.PENDING, StepStatus.RUNNING, StepStatus.FAILED, StepStatus.CANCELLED):
        put(database, run_id, status=status)
        assert send(database, run_id, event(AGAIN, 2)).status == status


def test_a_skip_is_final_without_a_run_and_records_its_round(
    database: Database, owner: User
) -> None:
    run_id = saved_run(database, owner)

    skipped = send(database, run_id, event(SKIPPED, round_=1))

    assert skipped.status == StepStatus.SKIPPED
    assert (skipped.output, skipped.tool_calls, skipped.verdict) == ("", [], None)
    assert (skipped.started_at, skipped.input_used, skipped.rounds) == (None, "the input", 1)
    assert skipped.finished_at is not None


def test_a_step_can_be_skipped_in_a_later_round_after_it_ran_or_was_skipped(
    database: Database, owner: User
) -> None:
    run_id = saved_run(database, owner)
    put(database, run_id, status=StepStatus.SUCCEEDED, output="old", verdict="pass")
    after_running = send(database, run_id, event(SKIPPED, round_=2))
    assert (after_running.status, after_running.output, after_running.rounds) == (
        StepStatus.SKIPPED,
        "",
        2,
    )
    assert after_running.verdict is None

    after_skipping = send(database, run_id, event(SKIPPED, round_=3))
    assert (after_skipping.status, after_skipping.rounds) == (StepStatus.SKIPPED, 3)


def test_a_step_that_is_running_or_stopped_cannot_be_marked_skipped(
    database: Database, owner: User
) -> None:
    run_id = saved_run(database, owner)
    for status in (StepStatus.RUNNING, StepStatus.FAILED, StepStatus.CANCELLED):
        put(database, run_id, status=status)
        assert send(database, run_id, event(SKIPPED)).status == status


def test_a_success_records_the_answer_and_the_verdict_it_gave(
    database: Database, owner: User
) -> None:
    run_id = saved_run(database, owner)
    put(database, run_id, status=StepStatus.RUNNING)

    done = send(database, run_id, event(DONE, 2, finished_result(2, Verdict.REVISE)))

    assert (done.status, done.output, done.verdict) == (StepStatus.SUCCEEDED, "new draft", "revise")
    assert done.finished_at is not None


def test_a_success_without_a_verdict_leaves_none(database: Database, owner: User) -> None:
    run_id = saved_run(database, owner)
    put(database, run_id, status=StepStatus.RUNNING)

    assert send(database, run_id, event(DONE, 1, finished_result(1))).verdict is None


def test_a_step_the_owner_stopped_keeps_that_whatever_its_agent_reports_later(
    database: Database, owner: User
) -> None:
    run_id = saved_run(database, owner)
    put(database, run_id, status=StepStatus.CANCELLED)

    for kind in (DONE, FAILED, CANCELLED, STARTED):
        stopped = send(database, run_id, event(kind, result=finished_result()))
        assert stopped.status == StepStatus.CANCELLED
