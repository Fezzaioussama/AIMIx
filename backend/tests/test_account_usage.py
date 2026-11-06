"""What an account spends of the server's key per day: added up over runs, chats and
planning, refused past the day's allowance, and shown under Settings → Usage."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from sqlalchemy.orm import Session

from api.exceptions import DailyLimitReached
from api.models import Run, RunStatus, UsageEvent, UsageKind, User
from api.repositories import usage as repository
from api.repositories.usage import NewUsageEvent
from api.services.account_usage import (
    AccountMeter,
    Calls,
    account_meter,
    calls_of,
    day_start,
    spent_today,
)
from api.services.llm import LLMProfile
from api.services.multiagent.step_agent import PipelineAgentGenerator, StepAgentDependencies
from api.services.run_budget import RunBudget
from api.services.run_policy import RunPolicy
from api.services.runs import RunService, RunStart
from config.settings import pin_settings
from llm.usage import UNMETERED, TokenUsage
from tests.conftest import TEST_SETTINGS, InlineRunExecutor, use_pipeline_generator
from tests.test_endpoints import make_pipeline
from tests.test_runs_api import start
from tests.test_step_agent_usage import loop_model
from tests.usage_fakes import EXACT_COST, UsageAgent

SERVER_KEY = LLMProfile("openrouter", "vendor/m")
OWN_KEY = LLMProfile("openrouter", "vendor/m", api_key="k")
A_CENT = 0.01


@pytest.fixture(autouse=True)
def tools_bind_to_the_fake_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(FakeMessagesListChatModel, "bind_tools", lambda self, tools, **kw: self)


@pytest.fixture
def allowance() -> Iterator[None]:
    """The server's key may be spent up to a cent a day; the test settings are back after."""
    pin_settings(TEST_SETTINGS.model_copy(update={"server_key_daily_max_cost_usd": A_CENT}))
    yield
    pin_settings(TEST_SETTINGS)


def now() -> datetime:
    return datetime.now(timezone.utc)


def record(session: Session, user: User, cost: float | None, when: datetime | None = None) -> None:
    """A chat call of 100 + 50 tokens at ``cost``, made at ``when`` (now by default)."""
    repository.record_event(
        session, NewUsageEvent(user.id, UsageKind.CHAT, "vendor/m", 100, 50, cost)
    )
    if when is not None:
        row = session.query(UsageEvent).order_by(UsageEvent.id.desc()).first()
        assert row is not None
        row.created_at = when
        session.commit()


def run_today(app: FastAPI, auth_client: TestClient, user: User, session: Session) -> Run:
    """A run of one step whose one model call costs EXACT_COST."""
    pipeline = make_pipeline(session, user, "Counted")
    use_pipeline_generator(app, UsageAgent())
    run = session.get(Run, start(auth_client, pipeline)["id"])
    assert run is not None
    return run


def test_the_days_spending_adds_runs_chats_and_planning(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    run_today(app, auth_client, user, session)
    record(session, user, 0.5)
    repository.record_event(
        session, NewUsageEvent(user.id, UsageKind.PLANNER, "vendor/m", 1000, 0, 0.25)
    )
    record(session, user, 9.0, when=now() - timedelta(days=1))  # yesterday: not today's

    spent = spent_today(session, user.id, now())

    assert spent == TokenUsage(1200, 100, EXACT_COST + 0.75, True)
    assert day_start(datetime(2026, 11, 6, 15, 30, tzinfo=timezone.utc)) == datetime(
        2026, 11, 6, tzinfo=timezone.utc
    )


def test_an_unpriced_call_counts_its_tokens_and_makes_the_cost_incomplete(
    session: Session, user: User
) -> None:
    record(session, user, 0.5)
    record(session, user, None)

    assert spent_today(session, user.id, now()) == TokenUsage(200, 100, 0.5, False)


def test_the_meter_refuses_a_call_once_the_allowance_is_used_up(
    app: FastAPI, session: Session, user: User
) -> None:
    calls = Calls(UsageKind.CHAT, "vendor/m", allowance=RunBudget(max_cost_usd=0.1))
    meter = AccountMeter(app.state.database, user.id, calls)

    meter.before_call()
    meter.after_call(TokenUsage.of(100, 50, 0.0625))
    meter.before_call()  # $0.0625 is under $0.10
    meter.after_call(TokenUsage.of(100, 50, 0.0625))

    with pytest.raises(DailyLimitReached) as refused:
        meter.before_call()
    assert refused.value.detail == (
        "Today's allowance of the server's key is used up: $0.12 of its $0.10 daily "
        "limit. Add your own API key on the Settings page, or come back after midnight UTC."
    )
    events = session.query(UsageEvent).all()
    assert [(e.kind, e.model, e.input_tokens, e.cost_usd) for e in events] == [
        (UsageKind.CHAT, "vendor/m", 100, 0.0625)
    ] * 2


def test_a_runs_calls_are_heard_but_not_kept_twice(
    app: FastAPI, session: Session, user: User
) -> None:
    meter = AccountMeter(app.state.database, user.id, Calls(None, "vendor/m"))

    meter.after_call(TokenUsage.of(100, 50, 0.5))

    assert session.query(UsageEvent).count() == 0


def test_whose_key_pays_decides_the_meter(app: FastAPI, user: User) -> None:
    bounded = Calls(None, "vendor/m", allowance=RunBudget(max_cost_usd=1.0))
    chat = Calls(UsageKind.CHAT, "vendor/m", allowance=RunBudget(max_cost_usd=1.0))

    assert account_meter(app.state.database, user.id, OWN_KEY, bounded) is UNMETERED
    own_chat = account_meter(app.state.database, user.id, OWN_KEY, chat)
    assert isinstance(own_chat, AccountMeter)
    assert own_chat.calls.allowance.max_cost_usd is None  # kept, never refused
    lent = account_meter(app.state.database, user.id, SERVER_KEY, bounded)
    assert isinstance(lent, AccountMeter)
    assert lent.calls.allowance.max_cost_usd == 1.0


def test_a_run_on_the_servers_key_stops_at_the_days_allowance(
    app: FastAPI, session: Session, user: User, allowance: None
) -> None:
    record(session, user, A_CENT)  # today's allowance is already spent
    generator = PipelineAgentGenerator(
        app.state.database,
        user,
        SERVER_KEY,
        StepAgentDependencies(lambda model: loop_model(), TEST_SETTINGS),
    )
    runs = RunService(app.state.database, InlineRunExecutor(), 1, RunPolicy())

    run = runs.start(user, make_pipeline(session, user, "Lent"), RunStart("go"), generator).run

    assert (run.status, run.error_code) == (RunStatus.FAILED, "daily_limit_reached")
    assert calls_of(None, "vendor/m").allowance.max_cost_usd == A_CENT


def test_the_usage_report_shows_todays_spending_against_the_allowance(
    app: FastAPI, auth_client: TestClient, user: User, session: Session, allowance: None
) -> None:
    run_today(app, auth_client, user, session)
    record(session, user, 0.5)

    report: dict[str, Any] = auth_client.get("/api/usage").json()

    assert report["other"]["cost_usd"] == 0.5
    assert report["usage"]["cost_usd"] == EXACT_COST + 0.5
    assert report["today"] == {
        "spent": {
            "input_tokens": 200,
            "output_tokens": 100,
            "cost_usd": EXACT_COST + 0.5,
            "cost_complete": True,
        },
        "max_cost_usd": A_CENT,
        "max_tokens": None,
    }


def test_an_account_with_its_own_key_has_no_allowance_to_show(
    auth_client: TestClient, user: User, session: Session, allowance: None
) -> None:
    from api.security import secret_box_for
    from api.services import llm_settings
    from api.services.llm_settings import ProviderChoice, SettingsUpdate

    choice = ProviderChoice("openrouter", TEST_SETTINGS.openrouter_default_model, "sk-or-1234")
    llm_settings.save(
        session, user, secret_box_for(TEST_SETTINGS), SettingsUpdate("openrouter", [choice])
    )

    today = auth_client.get("/api/usage").json()["today"]

    assert (today["max_cost_usd"], today["max_tokens"]) == (None, None)
