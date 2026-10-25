"""Resuming a run that stopped inside, or after, a review loop.

A step's row keeps the round it was last in, and a reviewer's row keeps its
verdict and answer: that is all a resumed run needs to pick the loop up where it
was, reuse what belongs to the round in progress, and not redo what is finished."""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest

from api.db import Database
from api.models import RunStatus, StepStatus, User
from api.repositories import runs
from api.repositories.runs import StepChange
from api.services.run_executor import BackgroundRunExecutor
from api.services.runs import RunService, RunStart, interrupt_abandoned_runs
from tests.approval_fakes import ParkedExecutor
from tests.flow.fakes import PASS, REVISE, ScriptedAgent
from tests.flow.support import WAIT_SECONDS, load, review_team, rounds, row, statuses, wait_for

FEEDBACK_TO_WRITER = (
    "p2 out-research\n\n"
    "Feedback from the reviewer (round 2 of 3):\n\nFix X.\n\n"
    "Revise your work to fix what the reviewer found."
)


def resume_to_the_end(
    database: Database, service: RunService, owner: User, run_id: int, agent: ScriptedAgent
) -> None:
    service.resume(owner, run_id, agent)
    wait_for(database, run_id, lambda run: run.status == RunStatus.SUCCEEDED)


@pytest.fixture
def second_executor() -> Iterator[BackgroundRunExecutor]:
    background = BackgroundRunExecutor(max_concurrent=2, grace_seconds=2.0)
    yield background
    background.shutdown()


def test_a_run_stopped_while_the_work_was_being_redone_redoes_it_with_the_feedback(
    database: Database, owner: User, service: RunService
) -> None:
    first = ScriptedAgent({"reviewer": [f"Fix X.\n{REVISE}"]}, hold={"writer": 2})
    started = service.start(owner, review_team(database, owner), RunStart("seed"), first)
    assert first.entered.wait(WAIT_SECONDS)
    service.cancel(owner, started.run.id)

    second = ScriptedAgent({"reviewer": [PASS]})
    resume_to_the_end(database, service, owner, started.run.id, second)

    # Research is kept; the writer goes on with round 2 and is told what the reviewer said
    # (read back from the reviewer's saved answer); the reviewer, whose row held round 1,
    # judges the new draft.
    assert second.roles() == ["writer", "reviewer"]
    assert second.prompts("writer") == [FEEDBACK_TO_WRITER]
    run = load(database, started.run.id)
    assert statuses(run) == [StepStatus.SUCCEEDED] * 3
    assert rounds(run) == [1, 2, 2]
    assert row(run, 3).verdict == "pass"
    assert second.prompts("reviewer") == ["p3 out-writer"]


def test_a_step_that_failed_in_a_later_round_is_run_again_in_that_round(
    database: Database, owner: User, service: RunService
) -> None:
    first = ScriptedAgent({"reviewer": [f"Fix X.\n{REVISE}"]}, fail={"writer": 2})
    started = service.start(owner, review_team(database, owner), RunStart("seed"), first)
    started.finished.result(timeout=WAIT_SECONDS)
    failed = load(database, started.run.id)
    assert statuses(failed) == [StepStatus.SUCCEEDED, StepStatus.FAILED, StepStatus.SUCCEEDED]
    assert rounds(failed) == [1, 2, 1]

    second = ScriptedAgent({"reviewer": [PASS]})
    resume_to_the_end(database, service, owner, started.run.id, second)

    assert second.roles() == ["writer", "reviewer"]
    assert second.prompts("writer") == [FEEDBACK_TO_WRITER]
    assert rounds(load(database, started.run.id)) == [1, 2, 2]


def test_a_reviewer_that_failed_in_a_later_round_is_run_again_on_the_kept_work(
    database: Database, owner: User, service: RunService
) -> None:
    first = ScriptedAgent(
        {"writer": ["draft v1", "draft v2"], "reviewer": [f"Fix X.\n{REVISE}"]},
        fail={"reviewer": 2},
    )
    started = service.start(owner, review_team(database, owner), RunStart("seed"), first)
    started.finished.result(timeout=WAIT_SECONDS)
    failed = load(database, started.run.id)
    assert statuses(failed) == [StepStatus.SUCCEEDED, StepStatus.SUCCEEDED, StepStatus.FAILED]
    assert rounds(failed) == [1, 2, 2]

    second = ScriptedAgent({"reviewer": ["Good.\n" + PASS]})
    resume_to_the_end(database, service, owner, started.run.id, second)

    # The writer's second draft belongs to the round in progress: it is kept, and judged.
    assert second.calls == [("reviewer", "p3 draft v2")]
    run = load(database, started.run.id)
    assert rounds(run) == [1, 2, 2]
    assert (row(run, 3).verdict, row(run, 3).output) == ("pass", "Good.")
    assert row(run, 2).output == "draft v2"


def test_a_run_that_stopped_between_two_rounds_sends_the_work_back_when_resumed(
    database: Database, owner: User, second_executor: BackgroundRunExecutor
) -> None:
    # The reviewer said REVISE and the process went away before the writer started again.
    parked = RunService(database, ParkedExecutor(), max_parallel_steps=4)
    run = parked.start(owner, review_team(database, owner), RunStart("seed"), ScriptedAgent()).run
    done = frozenset({StepStatus.PENDING})
    with database.session() as session:
        runs.set_status(session, run.id, [RunStatus.QUEUED], {"status": RunStatus.RUNNING})
        for order, text, verdict in (
            (1, "facts", None),
            (2, "draft v1", None),
            (3, "Fix X.", "revise"),
        ):
            values = {
                "status": StepStatus.SUCCEEDED,
                "input_used": "in",
                "output": text,
                "verdict": verdict,
            }
            runs.set_step(session, run.id, StepChange(order, done, values))
    assert interrupt_abandoned_runs(database) == 1

    agent = ScriptedAgent({"reviewer": [PASS]})
    service = RunService(database, second_executor, max_parallel_steps=4)
    resume_to_the_end(database, service, owner, run.id, agent)

    assert agent.roles() == ["writer", "reviewer"]
    assert agent.prompts("writer")[0].startswith(
        "p2 facts\n\nFeedback from the reviewer (round 2 of 3)"
    )
    assert "Fix X." in agent.prompts("writer")[0]
    assert rounds(load(database, run.id)) == [1, 2, 2]


def park_a_run_after_a_review(
    database: Database, owner: User, rounds: int, verdict: str, max_rounds: int = 2
) -> int:
    """A run the process left after its reviewer's answer in round ``rounds``."""
    parked = RunService(database, ParkedExecutor(), max_parallel_steps=4)
    pipeline = review_team(database, owner, max_rounds=max_rounds)
    run = parked.start(owner, pipeline, RunStart("seed"), ScriptedAgent()).run
    done = frozenset({StepStatus.PENDING})
    with database.session() as session:
        runs.set_status(session, run.id, [RunStatus.QUEUED], {"status": RunStatus.RUNNING})
        for order, text, verdict_ in (
            (1, "facts", None),
            (2, "draft", None),
            (3, "Fix Y.", verdict),
        ):
            values = {
                "status": StepStatus.SUCCEEDED,
                "input_used": "in",
                "output": text,
                "verdict": verdict_,
                "rounds": 1 if order == 1 else rounds,
            }
            runs.set_step(session, run.id, StepChange(order, done, values))
    assert interrupt_abandoned_runs(database) == 1
    return run.id


def test_a_run_stopped_after_a_second_review_sends_the_work_back_a_second_time(
    database: Database, owner: User, second_executor: BackgroundRunExecutor
) -> None:
    run_id = park_a_run_after_a_review(database, owner, rounds=2, verdict="revise")
    agent = ScriptedAgent({"reviewer": [PASS]})

    again = RunService(database, second_executor, max_parallel_steps=4)
    resume_to_the_end(database, again, owner, run_id, agent)

    # One time was already used: the loop has one more left, and the writer is in round 3.
    assert agent.roles() == ["writer", "reviewer"]
    assert "(round 3 of 3):\n\nFix Y." in agent.prompts("writer")[0]
    assert rounds(load(database, run_id)) == [1, 3, 3]


def test_a_run_stopped_after_the_last_allowed_review_goes_on_instead_of_looping(
    database: Database, owner: User, second_executor: BackgroundRunExecutor
) -> None:
    run_id = park_a_run_after_a_review(database, owner, rounds=3, verdict="revise")
    agent = ScriptedAgent()

    again = RunService(database, second_executor, max_parallel_steps=4)
    resume_to_the_end(database, again, owner, run_id, agent)

    assert agent.calls == []
    assert load(database, run_id).final_output == "Fix Y."


def test_a_run_interrupted_in_a_reviewers_round_keeps_the_new_draft(
    database: Database,
    owner: User,
    executor: BackgroundRunExecutor,
    second_executor: BackgroundRunExecutor,
) -> None:
    service = RunService(database, executor, max_parallel_steps=4)
    first = ScriptedAgent({"writer": ["v1", "v2"], "reviewer": [REVISE]}, hold={"reviewer": 2})
    started = service.start(owner, review_team(database, owner), RunStart("seed"), first)
    assert first.entered.wait(WAIT_SECONDS)

    executor.shutdown()

    interrupted = load(database, started.run.id)
    assert interrupted.status == RunStatus.INTERRUPTED
    assert statuses(interrupted)[2] == StepStatus.CANCELLED
    second = ScriptedAgent({"reviewer": [PASS]})
    again = RunService(database, second_executor, max_parallel_steps=4)
    resume_to_the_end(database, again, owner, started.run.id, second)
    assert second.calls == [("reviewer", "p3 v2")]


def test_a_finished_loop_is_not_run_again_when_a_later_step_is_resumed(
    database: Database, owner: User, service: RunService
) -> None:
    pipeline = review_team(database, owner, publisher=True)
    first = ScriptedAgent(
        {"writer": ["v1", "v2"], "reviewer": [REVISE, f"Good.\n{PASS}"]}, fail={"publisher": 1}
    )
    started = service.start(owner, pipeline, RunStart("seed"), first)
    started.finished.result(timeout=WAIT_SECONDS)
    assert load(database, started.run.id).status == RunStatus.FAILED

    second = ScriptedAgent()
    resume_to_the_end(database, service, owner, started.run.id, second)

    assert second.calls == [("publisher", "p4 Good.")]
    assert rounds(load(database, started.run.id)) == [1, 2, 2, 1]


def test_a_loop_that_ran_out_of_rounds_is_not_started_again_either(
    database: Database, owner: User, service: RunService
) -> None:
    pipeline = review_team(database, owner, max_rounds=1, publisher=True)
    first = ScriptedAgent({"reviewer": [f"Not yet.\n{REVISE}"]}, fail={"publisher": 1})
    started = service.start(owner, pipeline, RunStart("seed"), first)
    started.finished.result(timeout=WAIT_SECONDS)
    before = load(database, started.run.id)
    assert (row(before, 3).verdict, rounds(before)) == ("revise", [1, 2, 2, 1])

    second = ScriptedAgent()
    resume_to_the_end(database, service, owner, started.run.id, second)

    # Its rounds were used up: the loop is over, whatever the reviewer's last word was.
    assert second.roles() == ["publisher"]
    after = load(database, started.run.id)
    assert (after.status, rounds(after), row(after, 3).verdict) == (
        RunStatus.SUCCEEDED,
        [1, 2, 2, 1],
        "revise",
    )


def test_resuming_waits_for_nothing_when_every_step_is_already_done(
    database: Database, owner: User, service: RunService
) -> None:
    started = service.start(
        owner,
        review_team(database, owner),
        RunStart("seed"),
        ScriptedAgent({"reviewer": [REVISE, PASS]}),
    )
    started.finished.result(timeout=WAIT_SECONDS)
    agent = ScriptedAgent()

    assert service.resume(owner, started.run.id, agent).status == RunStatus.SUCCEEDED
    time.sleep(0.05)

    assert agent.calls == []
