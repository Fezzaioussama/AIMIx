"""The server's limits on every run: a default token limit that bounds a model
with no known price, and ceilings no caller can raise, on start and on resume."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.db import Database
from api.deps import app_settings
from api.exceptions import ValidationFailed
from api.models import Base, Run, RunStatus, User
from api.repositories import users
from api.services.run_budget import NO_BUDGET, RunBudget, RunLimits, default_budget, run_limits
from api.services.run_executor import BackgroundRunExecutor
from api.services.run_policy import RunPolicy, unset_ceilings, warn_about_unbounded_spending
from api.services.runs import RunService, RunStart
from config.settings import Settings
from tests.conftest import TEST_SETTINGS
from tests.test_endpoints import make_pipeline
from tests.usage_fakes import WAIT_SECONDS, ModelCall, UsageAgent, load_run, staged_pipeline

CEILING = RunBudget(max_cost_usd=1.0, max_tokens=10_000)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db = Database(f"sqlite:///{tmp_path / 'limits.sqlite3'}")
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


def service_with(
    database: Database, executor: BackgroundRunExecutor, limits: RunLimits
) -> RunService:
    return RunService(database, executor, 4, RunPolicy(limits))


# --- the rules ----------------------------------------------------------------------


def test_a_limit_above_the_ceiling_is_refused_and_says_the_most_allowed() -> None:
    limits = RunLimits(ceiling=CEILING)

    assert limits.allow(RunBudget(1.0, 10_000)) == RunBudget(1.0, 10_000)
    with pytest.raises(ValidationFailed) as cost:
        limits.allow(RunBudget(max_cost_usd=1.5))
    assert cost.value.detail == "Runs here may have at most a $1.00 limit; you asked for $1.50."
    with pytest.raises(
        ValidationFailed, match="at most a 10,000-token limit; you asked for 10,001"
    ):
        limits.allow(RunBudget(max_tokens=10_001))


def test_the_ceiling_caps_the_default_and_fills_a_limit_left_unset() -> None:
    limits = RunLimits(default=RunBudget(max_cost_usd=5.0), ceiling=CEILING)

    assert limits.applied(NO_BUDGET) == RunBudget(1.0, 10_000)
    assert limits.applied(RunBudget(0.25, 500)) == RunBudget(0.25, 500)
    # A limit saved before the ceiling was lowered is cut to it.
    assert limits.applied(NO_BUDGET, RunBudget(9.0, 90_000)) == RunBudget(1.0, 10_000)
    assert RunLimits().applied(NO_BUDGET) == NO_BUDGET


def test_the_limits_come_from_settings() -> None:
    configured = Settings(  # type: ignore[call-arg]
        _env_file=None,
        run_default_max_tokens=2000,
        run_max_cost_usd=3.0,
        run_max_tokens=50_000,
    )

    assert default_budget(configured) == RunBudget(None, 2000)
    assert run_limits(configured) == RunLimits(RunBudget(None, 2000), RunBudget(3.0, 50_000))
    assert run_limits(Settings(_env_file=None)) == RunLimits()  # type: ignore[call-arg]


@pytest.mark.parametrize("name", ["RUN_MAX_COST_USD", "RUN_MAX_TOKENS", "RUN_DEFAULT_MAX_TOKENS"])
def test_an_empty_limit_in_the_environment_is_none(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(name, "")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert getattr(settings, name.lower()) is None
    monkeypatch.setenv(name, "0")
    with pytest.raises(ValueError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_startup_warns_when_accounts_spend_the_servers_key_without_ceilings(
    caplog: pytest.LogCaptureFixture,
) -> None:
    open_key = TEST_SETTINGS.model_copy(update={"allow_server_llm_key": True})
    bounded = open_key.model_copy(
        update={"run_max_cost_usd": 5.0, "run_max_tokens": 10**6, "chat_max_tokens": 10**5}
    )

    with caplog.at_level(logging.WARNING, logger="api.services.run_policy"):
        warn_about_unbounded_spending(open_key)
        warn_about_unbounded_spending(bounded)
        warn_about_unbounded_spending(TEST_SETTINGS)

    assert len(caplog.records) == 1
    assert "unset=RUN_MAX_COST_USD,RUN_MAX_TOKENS,CHAT_MAX_TOKENS" in caplog.text
    # A cost ceiling alone leaves models with no known price unbounded.
    cost_only = open_key.model_copy(update={"run_max_cost_usd": 5.0})
    assert unset_ceilings(cost_only) == ["RUN_MAX_TOKENS", "CHAT_MAX_TOKENS"]


def test_the_app_checks_its_ceilings_when_it_is_built(monkeypatch: pytest.MonkeyPatch) -> None:
    from api import main

    seen: list[Settings] = []
    monkeypatch.setattr(main, "warn_about_unbounded_spending", seen.append)
    main.create_app()
    assert seen == [TEST_SETTINGS]


# --- runs ---------------------------------------------------------------------------


def test_a_run_asking_above_the_ceiling_is_refused_before_anything_is_saved(
    database: Database, owner: User, executor: BackgroundRunExecutor
) -> None:
    service = service_with(database, executor, RunLimits(ceiling=CEILING))
    pipeline = staged_pipeline(database, owner, [1])

    with pytest.raises(ValidationFailed, match=r"at most a \$1\.00 limit"):
        service.start(owner, pipeline, RunStart("seed", budget=RunBudget(5.0)), UsageAgent())

    with database.session() as session:
        assert session.query(Run).count() == 0


def test_a_run_that_sets_no_limit_gets_the_ceiling(
    database: Database, owner: User, executor: BackgroundRunExecutor
) -> None:
    service = service_with(database, executor, RunLimits(RunBudget(max_cost_usd=7.0), CEILING))
    pipeline = staged_pipeline(database, owner, [1])

    started = service.start(owner, pipeline, RunStart("seed"), UsageAgent())

    assert (started.run.max_cost_usd, started.run.max_tokens) == (1.0, 10_000)


def test_the_default_token_limit_stops_a_model_with_no_known_price(
    database: Database, owner: User, executor: BackgroundRunExecutor
) -> None:
    # A cost limit alone never stops it: its calls have no cost.
    limits = RunLimits(default=RunBudget(max_cost_usd=0.01, max_tokens=400))
    service = service_with(database, executor, limits)
    pipeline = staged_pipeline(database, owner, [1])
    agent = UsageAgent(calls={"role-1": 10}, call=ModelCall(cost_usd=None))

    started = service.start(owner, pipeline, RunStart("seed"), agent)
    started.finished.result(timeout=WAIT_SECONDS)

    run = load_run(database, started.run.id)
    assert (run.status, run.error_code) == (RunStatus.FAILED, "budget_exceeded")
    assert len(agent.reported) == 3


def test_resuming_cannot_raise_a_limit_past_the_ceiling(
    database: Database, owner: User, executor: BackgroundRunExecutor
) -> None:
    pipeline = staged_pipeline(database, owner, [1, 2])
    # Started before the operator set a ceiling, with a high limit of its own.
    before = service_with(database, executor, RunLimits())
    started = before.start(
        owner, pipeline, RunStart("seed", budget=RunBudget(9.0)), UsageAgent(fail=("role-2",))
    )
    started.finished.result(timeout=WAIT_SECONDS)
    after = service_with(database, executor, RunLimits(ceiling=CEILING))

    with pytest.raises(ValidationFailed, match=r"you asked for \$20\.00"):
        after.resume(owner, started.run.id, UsageAgent(), RunBudget(max_cost_usd=20.0))
    assert load_run(database, started.run.id).status == RunStatus.FAILED

    resumed = after.resume(owner, started.run.id, UsageAgent())

    # Its own $9 is cut to the ceiling, which also brings a token limit.
    assert (resumed.max_cost_usd, resumed.max_tokens) == (1.0, 10_000)


def test_the_api_refuses_a_limit_above_the_ceiling(
    app: FastAPI, auth_client: TestClient, session: Session, user: User
) -> None:
    capped = TEST_SETTINGS.model_copy(update={"run_max_cost_usd": 2.0})
    app.dependency_overrides[app_settings] = lambda: capped
    pipeline = make_pipeline(session, user, "Capped")

    response = auth_client.post(
        f"/api/pipelines/{pipeline.id}/runs", json={"input": "go", "max_cost_usd": 2.5}
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": "validation_error",
        "detail": "Runs here may have at most a $2.00 limit; you asked for $2.50.",
    }
