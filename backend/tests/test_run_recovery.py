"""Startup recovery: the runs a stopped process left behind are queued again by
themselves, as their owners would resume them, and one that cannot be says why."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from api.db import Database
from api.exceptions import ProviderNotConfigured
from api.models import Base, Pipeline, Run, RunStatus, User
from api.repositories import runs, users
from api.services.multiagent.contracts import StepAgent
from api.services.owner_agents import OwnerAgents
from api.services.run_recorder import utcnow
from api.services.run_recovery import NOT_RESUMED, Recovery, RecoveryPolicy, StartupRecovery
from api.services.runs import RunService, RunStart
from tests.conftest import InlineRunExecutor
from tests.test_runs_service import ParkedExecutor, ScriptedAgent, load, make_pipeline

RESUME_RECENT = RecoveryPolicy(auto_resume=True, max_age=timedelta(days=1))


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
def pipeline(database: Database, owner: User) -> Pipeline:
    return make_pipeline(database, owner, [1, 2])


class OwnerAgent:
    """Gives every resumed run the same agent, and records whose it was built for."""

    def __init__(self, agent: StepAgent) -> None:
        self.agent = agent
        self.owners: list[int] = []

    def __call__(self, session: Session, owner: User) -> StepAgent:
        self.owners.append(owner.id)
        return self.agent


class BrokenOnce(OwnerAgent):
    """Hits a bug (not a domain error) on its first call only."""

    def __init__(self, agent: StepAgent) -> None:
        super().__init__(agent)
        self.calls = 0

    def __call__(self, session: Session, owner: User) -> StepAgent:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("a bug")
        return super().__call__(session, owner)


class NoKey:
    """An owner without an API key, as ``ProfileAgents`` reports one."""

    def __call__(self, session: Session, owner: User) -> StepAgent:
        raise ProviderNotConfigured("No API key is set for openrouter.")


def abandoned(database: Database, owner: User, pipeline: Pipeline, text: str = "go") -> Run:
    """A run the previous process saved, then died before executing."""
    previous = RunService(database, ParkedExecutor(), max_parallel_steps=4)
    return previous.start(owner, pipeline, RunStart(text), ScriptedAgent()).run


def interrupted_at_shutdown(database: Database, run_id: int, when: datetime) -> None:
    """What the executor records on shutdown: nothing is active at the next start."""
    values = {"status": RunStatus.INTERRUPTED, "finished_at": when}
    with database.session() as session:
        assert runs.set_status(session, run_id, [RunStatus.QUEUED], values)


def recovery(
    database: Database, agents: OwnerAgents, policy: RecoveryPolicy = RESUME_RECENT
) -> StartupRecovery:
    """Resumed runs execute inline, so a test sees them finished."""
    service = RunService(database, InlineRunExecutor(), max_parallel_steps=4)
    return StartupRecovery(database, service, agents, policy)


def test_runs_a_stopped_process_left_active_are_resumed_at_startup(
    database: Database, owner: User, pipeline: Pipeline
) -> None:
    run = abandoned(database, owner, pipeline)
    agent = ScriptedAgent()
    agents = OwnerAgent(agent)

    recovered = recovery(database, agents).run()

    assert recovered == Recovery(interrupted=1, resumed=(run.id,))
    assert load(database, run.id).status == RunStatus.SUCCEEDED
    assert agent.calls == ["role-1", "role-2"]
    assert agents.owners == [owner.id]


def test_a_run_the_previous_shutdown_recorded_as_interrupted_is_resumed_too(
    database: Database, owner: User, pipeline: Pipeline
) -> None:
    run = abandoned(database, owner, pipeline)
    interrupted_at_shutdown(database, run.id, utcnow())

    recovered = recovery(database, OwnerAgent(ScriptedAgent())).run()

    assert recovered == Recovery(interrupted=0, resumed=(run.id,))
    assert load(database, run.id).status == RunStatus.SUCCEEDED


def test_a_run_interrupted_too_long_ago_is_left_to_its_owner(
    database: Database, owner: User, pipeline: Pipeline
) -> None:
    run = abandoned(database, owner, pipeline)
    interrupted_at_shutdown(database, run.id, utcnow() - timedelta(days=2))
    agent = ScriptedAgent()

    recovered = recovery(database, OwnerAgent(agent)).run()

    assert recovered == Recovery(interrupted=0)
    assert load(database, run.id).status == RunStatus.INTERRUPTED
    assert agent.calls == []


def test_a_run_whose_owner_has_no_key_stays_interrupted_with_the_reason(
    database: Database, owner: User, pipeline: Pipeline
) -> None:
    run = abandoned(database, owner, pipeline)

    recovered = recovery(database, NoKey()).run()

    assert recovered == Recovery(interrupted=1, left=(run.id,))
    left = load(database, run.id)
    assert left.status == RunStatus.INTERRUPTED
    assert left.error_code == "provider_not_configured"
    assert left.error_detail == NOT_RESUMED + "No API key is set for openrouter."
    # The next startup tries again: the owner may have saved a key since.
    again = recovery(database, OwnerAgent(ScriptedAgent())).run()
    assert again == Recovery(interrupted=0, resumed=(run.id,))
    assert load(database, run.id).status == RunStatus.SUCCEEDED


def test_a_bug_while_resuming_one_run_stops_neither_the_others_nor_the_start(
    database: Database, owner: User, pipeline: Pipeline
) -> None:
    first = abandoned(database, owner, pipeline, "one")
    second = abandoned(database, owner, pipeline, "two")

    recovered = recovery(database, BrokenOnce(ScriptedAgent())).run()

    assert recovered == Recovery(interrupted=2, resumed=(second.id,), left=(first.id,))
    left = load(database, first.id)
    assert (left.status, left.error_code) == (RunStatus.INTERRUPTED, "server_error")
    assert left.error_detail == NOT_RESUMED + "An unexpected error occurred."
    assert load(database, second.id).status == RunStatus.SUCCEEDED


def test_with_auto_resume_off_interrupted_runs_wait_for_their_owners(
    database: Database, owner: User, pipeline: Pipeline
) -> None:
    run = abandoned(database, owner, pipeline)
    policy = RecoveryPolicy(auto_resume=False, max_age=timedelta(days=1))
    agent = ScriptedAgent()

    recovered = recovery(database, OwnerAgent(agent), policy).run()

    assert recovered == Recovery(interrupted=1)
    assert load(database, run.id).status == RunStatus.INTERRUPTED
    assert agent.calls == []
