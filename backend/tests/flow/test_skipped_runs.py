"""Conditional steps in a recorded run: what a skipped step's row holds, and that
a resumed run keeps it instead of judging the condition again."""

from __future__ import annotations

from api.db import Database
from api.models import Pipeline, RunStatus, StepStatus, User
from api.repositories import runs
from api.repositories.runs import StepChange
from api.services.runs import RunService, RunStart
from tests.flow.fakes import ScriptedAgent, stored_step
from tests.flow.support import WAIT_SECONDS, load, row, save_pipeline, statuses, wait_for

BLOG_ONLY = {"source": "previous_output", "operator": "contains", "value": "blog"}
TOPIC_IS_BEES = {"source": "input:topic", "operator": "equals", "value": "bees"}
TOPIC = {"name": "topic", "label": "", "description": ""}


def team(database: Database, owner: User) -> Pipeline:
    """research (1) -> seo, only if the post is for a blog (2) -> publish (3)."""
    return save_pipeline(
        database,
        owner,
        stored_step(1, 1, "research"),
        stored_step(2, 2, "seo", condition=BLOG_ONLY),
        stored_step(3, 3, "publish"),
    )


def test_a_skipped_step_is_recorded_without_having_run(
    database: Database, owner: User, service: RunService
) -> None:
    agent = ScriptedAgent({"research": ["a post for the newsletter"]})

    started = service.start(owner, team(database, owner), RunStart("seed"), agent)
    outcome = started.finished.result(timeout=WAIT_SECONDS)

    assert agent.roles() == ["research", "publish"]
    assert outcome.result is not None
    run = load(database, started.run.id)
    assert run.status == RunStatus.SUCCEEDED
    assert statuses(run) == [StepStatus.SUCCEEDED, StepStatus.SKIPPED, StepStatus.SUCCEEDED]
    seo = row(run, 2)
    assert (seo.output, seo.tool_calls, seo.rounds, seo.error_code) == ("", [], 1, "")
    assert seo.input_used == "a post for the newsletter"
    assert seo.started_at is None and seo.finished_at is not None
    # The stage after it was handed what the skipped stage was handed.
    assert agent.prompts("publish") == ["p3 a post for the newsletter"]


def test_a_step_whose_condition_holds_is_recorded_like_any_other(
    database: Database, owner: User, service: RunService
) -> None:
    agent = ScriptedAgent({"research": ["a post for the BLOG"]})

    started = service.start(owner, team(database, owner), RunStart("seed"), agent)
    started.finished.result(timeout=WAIT_SECONDS)

    run = load(database, started.run.id)
    assert statuses(run) == [StepStatus.SUCCEEDED] * 3
    assert row(run, 2).started_at is not None


def test_a_condition_can_read_a_named_input_of_the_run(
    database: Database, owner: User, service: RunService
) -> None:
    pipeline = save_pipeline(
        database,
        owner,
        stored_step(1, 1, "research"),
        stored_step(2, 2, "seo", condition=TOPIC_IS_BEES),
        inputs=[TOPIC],
    )
    agent = ScriptedAgent()

    started = service.start(owner, pipeline, RunStart(values={"topic": "Bees"}), agent)
    started.finished.result(timeout=WAIT_SECONDS)

    assert agent.roles() == ["research", "seo"]


def test_resuming_keeps_a_skipped_step_and_goes_on_from_the_one_that_failed(
    database: Database, owner: User, service: RunService
) -> None:
    first = ScriptedAgent({"research": ["a post for the newsletter"]}, fail={"publish": 1})
    started = service.start(owner, team(database, owner), RunStart("seed"), first)
    started.finished.result(timeout=WAIT_SECONDS)
    failed = load(database, started.run.id)
    assert statuses(failed) == [StepStatus.SUCCEEDED, StepStatus.SKIPPED, StepStatus.FAILED]

    second = ScriptedAgent()
    service.resume(owner, started.run.id, second)
    run = wait_for(database, started.run.id, lambda r: r.status == RunStatus.SUCCEEDED)

    # Only the failed step ran again; the skipped one was neither judged nor started.
    assert second.calls == [("publish", "p3 a post for the newsletter")]
    assert statuses(run) == [StepStatus.SUCCEEDED, StepStatus.SKIPPED, StepStatus.SUCCEEDED]
    assert row(run, 2).finished_at == row(failed, 2).finished_at


def test_a_kept_skip_is_final_even_when_its_condition_would_hold_now(
    database: Database, owner: User, service: RunService
) -> None:
    first = ScriptedAgent({"research": ["newsletter"]}, fail={"publish": 1})
    started = service.start(owner, team(database, owner), RunStart("seed"), first)
    started.finished.result(timeout=WAIT_SECONDS)
    # Change what the first step handed on, so the condition would now be true.
    with database.session() as session:
        saved = frozenset({StepStatus.SUCCEEDED})
        runs.set_step(session, started.run.id, StepChange(1, saved, {"output": "a blog post"}))

    second = ScriptedAgent()
    service.resume(owner, started.run.id, second)
    run = wait_for(database, started.run.id, lambda r: r.status == RunStatus.SUCCEEDED)

    assert second.calls == [("publish", "p3 a blog post")]
    assert row(run, 2).status == StepStatus.SKIPPED
