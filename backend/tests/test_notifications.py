"""Emails about runs and schedules: a run that ended, a run waiting for its owner, a
schedule that could not start; only to an account with an address and the switch
on, and never a failure that reaches the run."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from api.exceptions import ProviderUnavailable
from api.models import ApprovalStatus, Run, RunStatus, User
from api.repositories import users
from api.services.agent_types import AgentOutcome, AgentTask, RunStepRef
from api.services.approvals.gate import GateHooks, RunApprovalGate, ToolRequest
from api.services.email import NullSender
from api.services.multiagent.contracts import StepAgent
from api.services.notifications import NotificationLinks, Notifier, excerpt
from api.services.run_policy import RunPolicy
from api.services.runs import RunService, RunStart
from api.services.schedules.scheduler import Scheduler, SchedulerHooks
from tests.approval_fakes import (
    ARGUMENTS,
    FAST_LIMITS,
    file_database,
    make_owner,
    make_pipeline,
    recording_tool,
    reply_as,
    running_run,
)
from tests.conftest import FakeProvider, InlineRunExecutor
from tests.email_fakes import Outbox, Refusing
from tests.schedules.support import TOMORROW, Clock, FlakyAgents, new_schedule, run_service
from tests.test_endpoints import make_pipeline as make_api_pipeline

ADDRESS = "alice@example.com"
LINKS = NotificationLinks("https://app.test")


class Failing:
    async def execute(self, task: AgentTask) -> AgentOutcome:
        raise ProviderUnavailable("the model is down")


def notifier(sender: Outbox | Refusing | NullSender, max_chars: int = 4_000) -> Notifier:
    return Notifier(sender, LINKS, max_chars)


@pytest.fixture
def addressed(session: Session, user: User) -> User:
    users.set_email(session, user, ADDRESS)
    return user


def ended_run(app: FastAPI, session: Session, owner: User, agent: StepAgent) -> Run:
    """A run of a new "Digest" pipeline, ended inline, nobody told."""
    pipeline = make_api_pipeline(session, owner, "Digest")
    runs = RunService(app.state.database, InlineRunExecutor(), 1, RunPolicy())
    return runs.start(owner, pipeline, RunStart("bees"), agent).run


def test_a_finished_run_is_told_with_a_link_and_the_start_of_its_result(
    app: FastAPI, session: Session, addressed: User
) -> None:
    run = ended_run(app, session, addressed, FakeProvider("Buzz " * 10))
    outbox = Outbox()

    assert notifier(outbox, max_chars=12).run_ended(app.state.database, run.id)

    (email,) = outbox.sent
    assert (email.to, email.subject) == (ADDRESS, '"Digest" finished')
    assert f"https://app.test/runs/{run.id}" in email.text
    assert "Buzz Buzz Bu…" in email.text
    assert "The rest is on the run's page." in email.text


def test_a_failed_run_is_told_with_the_reason(
    app: FastAPI, session: Session, addressed: User
) -> None:
    run = ended_run(app, session, addressed, Failing())
    outbox = Outbox()

    assert notifier(outbox).run_ended(app.state.database, run.id)

    (email,) = outbox.sent
    assert email.subject == '"Digest" failed'
    assert "failed: the model is down" in email.text
    assert "Resume" in email.text


def test_nothing_is_sent_without_an_address_or_with_the_switch_off(
    app: FastAPI, session: Session, user: User
) -> None:
    run = ended_run(app, session, user, FakeProvider())
    outbox = Outbox()

    assert not notifier(outbox).run_ended(app.state.database, run.id)
    users.set_email(session, user, ADDRESS)
    users.set_email_notifications(session, user, False)
    assert not notifier(outbox).run_ended(app.state.database, run.id)

    assert outbox.sent == []
    assert not notifier(outbox).run_ended(app.state.database, 999)


def test_a_sender_that_fails_or_is_missing_never_raises(
    app: FastAPI, session: Session, addressed: User
) -> None:
    run = ended_run(app, session, addressed, FakeProvider())

    assert not notifier(Refusing()).run_ended(app.state.database, run.id)
    assert not notifier(NullSender()).run_ended(app.state.database, run.id)


def test_the_run_service_tells_the_owner_when_a_run_ends(
    app: FastAPI, session: Session, addressed: User
) -> None:
    outbox = Outbox()
    pipeline = make_api_pipeline(session, addressed, "Digest")
    policy = RunPolicy(notifications=notifier(outbox))
    runs = RunService(app.state.database, InlineRunExecutor(), 1, policy)

    run = runs.start(addressed, pipeline, RunStart("bees"), FakeProvider("Buzz")).run

    assert run.status == RunStatus.SUCCEEDED
    assert [email.subject for email in outbox.sent] == ['"Digest" finished']


def test_the_owner_is_told_once_when_a_run_starts_waiting(tmp_path: Path) -> None:
    database = file_database(tmp_path)
    owner = make_owner(database)
    run_id = running_run(database, owner, make_pipeline(database, owner))
    with database.session() as session:
        row = users.get(session, owner.id)
        assert row is not None
        users.set_email(session, row, ADDRESS)
    outbox = Outbox()
    hooks = GateHooks(on_waiting=notifier(outbox).run_waiting)
    gate = RunApprovalGate(database, RunStepRef(run_id, 1), FAST_LIMITS, hooks)
    request = ToolRequest(recording_tool("crm_send_email", []), "crm", ARGUMENTS)

    async def ask_twice() -> list[ApprovalStatus]:
        answers = []
        for _ in range(2):
            asked = asyncio.create_task(gate.ask(request))
            await reply_as(database, owner, run_id, ApprovalStatus.APPROVED)
            answers.append(await asked)
        return answers

    try:
        assert asyncio.run(ask_twice()) == [ApprovalStatus.APPROVED] * 2
    finally:
        database.engine.dispose()
    (email,) = outbox.sent
    assert email.subject == '"Flow" is waiting for you'
    assert f"https://app.test/runs/{run_id}" in email.text


def test_a_schedule_that_cannot_start_is_told_once_per_reason(
    app: FastAPI, session: Session, addressed: User
) -> None:
    pipeline = make_api_pipeline(session, addressed, "Digest")
    new_schedule(session, addressed, pipeline.id)  # next: 25 Oct, 09:00 UTC
    outbox = Outbox()
    clock = Clock(TOMORROW)
    agents = FlakyAgents(FakeProvider(), failures=2)
    ticking = Scheduler(
        app.state.database, run_service(app), agents, SchedulerHooks(clock, notifier(outbox))
    )

    assert ticking.tick() == 0
    clock.advance(days=1)
    assert ticking.tick() == 0  # the same reason again: no second email
    clock.advance(days=1)
    assert ticking.tick() == 1  # and nothing is said about a run that starts

    (email,) = outbox.sent
    assert email.subject == '"Digest" could not run as scheduled'
    assert "No API key is set for openrouter." in email.text
    assert "https://app.test/schedules" in email.text


def test_an_excerpt_is_cut_with_a_note() -> None:
    assert excerpt("  short  ", 10) == "short"
    assert excerpt("x" * 20, 5) == "xxxxx…\n\n(The rest is on the run's page.)"
