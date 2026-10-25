"""Usage and spending limits on background runs, end to end: the real executor,
a file database (one connection per thread) and step agents that report their
model calls to the run's meter like the real agent does."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from api.db import Database
from api.exceptions import BudgetExceeded
from api.models import Base, RunStatus, StepStatus, User
from api.repositories import users
from api.services.run_budget import NO_BUDGET, RunBudget
from api.services.run_executor import BackgroundRunExecutor
from api.services.runs import RunService, RunStart
from api.services.usage import total_usage
from tests.usage_fakes import (
    EXACT_COST,
    WAIT_SECONDS,
    ModelCall,
    UsageAgent,
    load_run,
    staged_pipeline,
    wait_for_run,
)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db = Database(f"sqlite:///{tmp_path / 'usage.sqlite3'}")
    Base.metadata.create_all(db.engine)
    yield db
    db.engine.dispose()


@pytest.fixture
def owner(database: Database) -> User:
    with database.session() as session:
        return users.create(session, "spender", "hash")


@pytest.fixture
def executor() -> Iterator[BackgroundRunExecutor]:
    background = BackgroundRunExecutor(max_concurrent=2, grace_seconds=2.0)
    yield background
    background.shutdown()


@pytest.fixture
def service(database: Database, executor: BackgroundRunExecutor) -> RunService:
    return RunService(database, executor, max_parallel_steps=4, default_limits=NO_BUDGET)


def run_to_the_end(service: RunService, owner: User, database: Database, **start: object) -> int:
    pipeline = staged_pipeline(database, owner, [1, 2, 2])
    agent = start.pop("agent")
    assert isinstance(agent, UsageAgent)
    started = service.start(owner, pipeline, RunStart("seed", **start), agent)  # type: ignore[arg-type]
    started.finished.result(timeout=WAIT_SECONDS)
    return started.run.id


def test_every_step_records_what_its_model_calls_used(
    database: Database, owner: User, service: RunService
) -> None:
    pipeline = staged_pipeline(database, owner, [1, 2, 2])
    agent = UsageAgent(calls={"role-1": 3, "role-2": 2, "role-3": 1})

    started = service.start(owner, pipeline, RunStart("seed"), agent)
    outcome = started.finished.result(timeout=WAIT_SECONDS)

    run = load_run(database, started.run.id)
    assert run.status == RunStatus.SUCCEEDED
    assert [(step.input_tokens, step.output_tokens) for step in run.steps] == [
        (300, 150),
        (200, 100),
        (100, 50),
    ]
    assert [step.cost_usd for step in run.steps] == [
        pytest.approx(3 * EXACT_COST),
        pytest.approx(2 * EXACT_COST),
        pytest.approx(EXACT_COST),
    ]
    totals = total_usage(run.steps)
    assert (totals.input_tokens, totals.output_tokens) == (600, 300)
    assert totals.cost_usd == pytest.approx(6 * EXACT_COST)
    assert totals.cost_complete is True
    # The same numbers reach whoever waits for the run, step by step.
    assert outcome.result is not None
    waiting = [item.usage.total_tokens for item in outcome.result.intermediate_results]
    assert waiting == [450, 300, 150]


def test_a_model_whose_cost_is_unknown_still_has_its_tokens_counted(
    database: Database, owner: User, service: RunService
) -> None:
    agent = UsageAgent(call=ModelCall(cost_usd=None))

    run_id = run_to_the_end(service, owner, database, agent=agent)

    run = load_run(database, run_id)
    assert [step.cost_usd for step in run.steps] == [None, None, None]
    assert [step.input_tokens for step in run.steps] == [100, 100, 100]
    totals = total_usage(run.steps)
    assert (totals.total_tokens, totals.cost_usd, totals.cost_complete) == (450, None, False)


def test_a_failed_step_keeps_what_it_spent_before_it_failed(
    database: Database, owner: User, service: RunService
) -> None:
    agent = UsageAgent(calls={"role-1": 2}, fail=("role-1",))
    pipeline = staged_pipeline(database, owner, [1, 2, 2])

    started = service.start(owner, pipeline, RunStart("seed"), agent)
    started.finished.result(timeout=WAIT_SECONDS)

    run = load_run(database, started.run.id)
    assert (run.status, run.error_code) == (RunStatus.FAILED, "provider_unavailable")
    assert run.steps[0].status == StepStatus.FAILED
    assert run.steps[0].input_tokens == 200
    assert run.steps[0].cost_usd == pytest.approx(2 * EXACT_COST)


def test_a_stopped_run_keeps_the_usage_of_the_step_it_stopped(
    database: Database, owner: User, service: RunService
) -> None:
    agent = UsageAgent(calls={"role-1": 2}, hold=("role-1",))
    pipeline = staged_pipeline(database, owner, [1, 2])
    started = service.start(owner, pipeline, RunStart("seed"), agent)
    wait_for_run(database, started.run.id, lambda run: len(agent.reported) == 2)

    stopped = service.cancel(owner, started.run.id)

    assert stopped.status == RunStatus.CANCELLED
    assert (stopped.steps[0].input_tokens, stopped.steps[0].output_tokens) == (200, 100)
    assert total_usage(stopped.steps).cost_usd == pytest.approx(2 * EXACT_COST)


def test_a_run_that_reaches_its_cost_limit_stops_failed_and_keeps_its_finished_steps(
    database: Database, owner: User, service: RunService
) -> None:
    # Step 1 spends $0.0625; steps 2 and 3 then run side by side, 20 calls each.
    agent = UsageAgent(calls={"role-1": 1, "role-2": 20, "role-3": 20})
    pipeline = staged_pipeline(database, owner, [1, 2, 2])

    started = service.start(
        owner, pipeline, RunStart("seed", budget=RunBudget(max_cost_usd=0.5)), agent
    )
    outcome = started.finished.result(timeout=WAIT_SECONDS)

    run = load_run(database, started.run.id)
    assert isinstance(outcome.error, BudgetExceeded)
    assert (run.status, run.error_code) == (RunStatus.FAILED, "budget_exceeded")
    assert re.fullmatch(
        r"This run stopped at \$0\.\d{2} because it reached its \$0\.50 limit\.", run.error_detail
    )
    # Finished work is kept, and the steps that were running are not.
    assert (run.steps[0].status, run.steps[0].output) == (StepStatus.SUCCEEDED, "out-role-1")
    assert {step.status for step in run.steps[1:]} <= {StepStatus.FAILED, StepStatus.CANCELLED}
    assert StepStatus.FAILED in {step.status for step in run.steps[1:]}
    failed = next(step for step in run.steps if step.status == StepStatus.FAILED)
    assert failed.error_code == "budget_exceeded"
    # It stopped at the limit: at most one call per parallel step was already in flight.
    spent = total_usage(run.steps).cost_usd
    assert spent is not None and 0.5 <= spent <= 0.5 + 2 * EXACT_COST


def test_parallel_steps_never_double_count_or_lose_a_call_when_the_limit_stops_them(
    database: Database, owner: User, service: RunService
) -> None:
    agent = UsageAgent(calls={"role-1": 1, "role-2": 20, "role-3": 20})
    pipeline = staged_pipeline(database, owner, [1, 2, 2])

    started = service.start(
        owner, pipeline, RunStart("seed", budget=RunBudget(max_cost_usd=0.5)), agent
    )
    started.finished.result(timeout=WAIT_SECONDS)

    run = load_run(database, started.run.id)
    # What the database holds is exactly what the finished calls reported: every
    # one counted once, per step and in all.
    for step in run.steps:
        expected = agent.reported_by(step.title or f"role-{step.step_order}")
        assert (step.input_tokens, step.output_tokens) == (
            expected.input_tokens,
            expected.output_tokens,
        )
        assert (step.cost_usd or 0.0) == pytest.approx(expected.cost_usd or 0.0)
    totals = total_usage(run.steps)
    reported = agent.reported_total()
    assert totals.total_tokens == reported.total_tokens
    assert totals.cost_usd == pytest.approx(reported.cost_usd)
    assert len(agent.reported) == round((totals.cost_usd or 0.0) / EXACT_COST)


def test_a_token_limit_stops_a_run_whose_cost_is_unknown(
    database: Database, owner: User, service: RunService
) -> None:
    agent = UsageAgent(calls={"role-1": 10}, call=ModelCall(cost_usd=None))
    pipeline = staged_pipeline(database, owner, [1])

    started = service.start(
        owner, pipeline, RunStart("seed", budget=RunBudget(max_tokens=400)), agent
    )
    started.finished.result(timeout=WAIT_SECONDS)

    run = load_run(database, started.run.id)
    assert (run.status, run.error_code) == (RunStatus.FAILED, "budget_exceeded")
    # 150 tokens a call: the third call brought it to 450, so a fourth was refused.
    assert run.error_detail == (
        "This run stopped at 450 tokens because it reached its 400-token limit."
    )
    assert len(agent.reported) == 3


def test_a_cost_limit_cannot_stop_a_run_whose_cost_is_unknown(
    database: Database, owner: User, service: RunService
) -> None:
    agent = UsageAgent(calls={"role-1": 10}, call=ModelCall(cost_usd=None))
    pipeline = staged_pipeline(database, owner, [1])

    started = service.start(
        owner, pipeline, RunStart("seed", budget=RunBudget(max_cost_usd=0.01)), agent
    )
    started.finished.result(timeout=WAIT_SECONDS)

    run = load_run(database, started.run.id)
    assert run.status == RunStatus.SUCCEEDED
    assert total_usage(run.steps).total_tokens == 1500


def stopped_by_budget(
    service: RunService, owner: User, database: Database, budget: RunBudget
) -> tuple[int, UsageAgent]:
    """A three-step run that fills its $0.50 limit during its parallel stage."""
    agent = UsageAgent(calls={"role-1": 1, "role-2": 20, "role-3": 20})
    pipeline = staged_pipeline(database, owner, [1, 2, 2])
    started = service.start(owner, pipeline, RunStart("seed", budget=budget), agent)
    started.finished.result(timeout=WAIT_SECONDS)
    assert load_run(database, started.run.id).error_code == "budget_exceeded"
    return started.run.id, agent


def test_resuming_with_a_higher_limit_continues_and_keeps_every_earlier_cost(
    database: Database, owner: User, service: RunService
) -> None:
    run_id, _ = stopped_by_budget(service, owner, database, RunBudget(max_cost_usd=0.5))
    before = load_run(database, run_id)
    spent_before = total_usage(before.steps)
    second_try = UsageAgent()

    resumed = service.resume(owner, run_id, second_try, RunBudget(max_cost_usd=5.0))

    assert resumed.max_cost_usd == 5.0
    run = wait_for_run(database, run_id, lambda again: again.status == RunStatus.SUCCEEDED)
    # Step 1 had finished, so it is not run again; the others are.
    assert sorted(second_try.executed) == ["role-2", "role-3"]
    assert (run.error_code, run.error_detail) == ("", "")
    assert run.max_cost_usd == 5.0
    totals = total_usage(run.steps)
    assert totals.total_tokens == spent_before.total_tokens + 2 * 150
    assert totals.cost_usd == pytest.approx((spent_before.cost_usd or 0.0) + 2 * EXACT_COST)


def test_resuming_under_the_limit_that_stopped_it_is_refused_and_changes_nothing(
    database: Database, owner: User, service: RunService
) -> None:
    run_id, _ = stopped_by_budget(service, owner, database, RunBudget(max_cost_usd=0.5))
    agent = UsageAgent()

    with pytest.raises(BudgetExceeded, match=r"already reached its \$0\.50 limit"):
        service.resume(owner, run_id, agent)
    with pytest.raises(BudgetExceeded):
        service.resume(owner, run_id, agent, RunBudget(max_cost_usd=0.5))

    run = load_run(database, run_id)
    assert (run.status, run.error_code) == (RunStatus.FAILED, "budget_exceeded")
    assert agent.executed == []


def test_resume_can_add_a_token_limit_and_keeps_the_cost_limit_it_did_not_change(
    database: Database, owner: User, service: RunService
) -> None:
    run_id, _ = stopped_by_budget(service, owner, database, RunBudget(max_cost_usd=0.5))

    service.resume(owner, run_id, UsageAgent(), RunBudget(max_cost_usd=9.0, max_tokens=50_000))
    wait_for_run(database, run_id, lambda run: run.status == RunStatus.SUCCEEDED)
    run = load_run(database, run_id)
    assert (run.max_cost_usd, run.max_tokens) == (9.0, 50_000)


def test_resume_without_a_new_limit_keeps_the_runs_own(
    database: Database, owner: User, service: RunService
) -> None:
    pipeline = staged_pipeline(database, owner, [1, 2])
    failing = UsageAgent(fail=("role-2",))
    started = service.start(
        owner,
        pipeline,
        RunStart("seed", budget=RunBudget(max_cost_usd=2.0, max_tokens=9000)),
        failing,
    )
    started.finished.result(timeout=WAIT_SECONDS)

    service.resume(owner, started.run.id, UsageAgent())

    run = wait_for_run(database, started.run.id, lambda again: again.status == RunStatus.SUCCEEDED)
    assert (run.max_cost_usd, run.max_tokens) == (2.0, 9000)


def test_a_run_started_without_limits_takes_the_servers_default(
    database: Database, owner: User, executor: BackgroundRunExecutor
) -> None:
    service = RunService(database, executor, 4, default_limits=RunBudget(max_cost_usd=0.25))
    pipeline = staged_pipeline(database, owner, [1])

    plain = service.start(owner, pipeline, RunStart("seed"), UsageAgent())
    own_cost = service.start(
        owner, pipeline, RunStart("seed", budget=RunBudget(max_cost_usd=1.0)), UsageAgent()
    )
    tokens_only = service.start(
        owner, pipeline, RunStart("seed", budget=RunBudget(max_tokens=100)), UsageAgent()
    )

    assert (plain.run.max_cost_usd, plain.run.max_tokens) == (0.25, None)
    assert (own_cost.run.max_cost_usd, own_cost.run.max_tokens) == (1.0, None)
    assert (tokens_only.run.max_cost_usd, tokens_only.run.max_tokens) == (0.25, 100)


def test_the_default_limit_stops_a_run_that_set_none(
    database: Database, owner: User, executor: BackgroundRunExecutor
) -> None:
    service = RunService(database, executor, 4, default_limits=RunBudget(max_cost_usd=0.25))
    pipeline = staged_pipeline(database, owner, [1])

    started = service.start(owner, pipeline, RunStart("seed"), UsageAgent(calls={"role-1": 50}))
    started.finished.result(timeout=WAIT_SECONDS)

    run = load_run(database, started.run.id)
    assert (run.status, run.error_code) == (RunStatus.FAILED, "budget_exceeded")
    assert run.error_detail == "This run stopped at $0.25 because it reached its $0.25 limit."


def test_without_any_limit_a_run_is_never_stopped_for_cost(
    database: Database, owner: User, service: RunService
) -> None:
    agent = UsageAgent(calls={"role-1": 40})
    pipeline = staged_pipeline(database, owner, [1])

    started = service.start(owner, pipeline, RunStart("seed"), agent)
    started.finished.result(timeout=WAIT_SECONDS)

    run = load_run(database, started.run.id)
    assert run.status == RunStatus.SUCCEEDED
    assert (run.max_cost_usd, run.max_tokens) == (None, None)
    assert total_usage(run.steps).cost_usd == pytest.approx(40 * EXACT_COST)
