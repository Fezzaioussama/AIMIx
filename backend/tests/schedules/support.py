"""Shared by the schedules tests: a clock the test sets, fake owner agents, builders and
the small helpers of the HTTP tests. Nothing here waits for real time."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.exceptions import ProviderNotConfigured
from api.models import Pipeline, Run, Schedule, ScheduleFrequency, User
from api.services.multiagent.contracts import StepAgent
from api.services.runs import RunService, RunStart
from api.services.schedules.scheduler import Scheduler
from api.services.schedules.service import ScheduleAccess, ScheduleDraft, ScheduleView, create
from api.services.schedules.timing import Timing, next_run_after
from tests.conftest import InlineRunExecutor

PARIS = "Europe/Paris"
#: A Saturday noon in UTC: 14:00 in Paris, just before the clocks go back there.
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
#: 12:00 on the 25th, after that day's 09:00 time.
TOMORROW = NOW + timedelta(days=1)
WAIT_SECONDS = 5.0
DAILY_AT_NINE = Timing(ScheduleFrequency.DAILY, "UTC", time(9, 0))
HOURLY_AT_QUARTER_PAST = Timing(ScheduleFrequency.HOURLY, "UTC", time(0, 15))


# --- time -------------------------------------------------------------------------


def utc(*parts: int) -> datetime:
    """``utc(2026, 10, 25, 9)``: a UTC instant from year, month, day, hour, minute."""
    return datetime(*parts, tzinfo=timezone.utc)


def when(day: int, hour: int, minute: int = 0, month: int = 10) -> datetime:
    """A UTC instant in 2026, October unless a month is given."""
    return datetime(2026, month, day, hour, minute, tzinfo=timezone.utc)


def parse(text: str) -> datetime:
    """An ISO time as the API sends it (``...Z``)."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def at_utc(moment: datetime | None) -> datetime:
    """A stored time (SQLite hands back naive UTC) as an aware one."""
    assert moment is not None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def chain(timing: Timing, start: datetime, count: int) -> list[datetime]:
    """The next ``count`` times, each found after the one before."""
    found: list[datetime] = []
    at = start
    for _ in range(count):
        at = next_run_after(timing, at)
        found.append(at)
    return found


def local(moment: datetime, zone: str) -> str:
    """A UTC instant as that zone's wall clock, with its offset: 2026-03-29 03:30+0200."""
    return moment.astimezone(ZoneInfo(zone)).strftime("%Y-%m-%d %H:%M%z")


class Clock:
    """A clock the test sets: pass it to ``Scheduler``, or override ``utcnow`` with it."""

    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


# --- the scheduler ------------------------------------------------------------------


class StaticAgents:
    """Gives every schedule's run the same step agent, and records whose it was built for."""

    def __init__(self, agent: StepAgent) -> None:
        self.agent = agent
        self.owners: list[int] = []

    def __call__(self, session: Session, owner: User) -> StepAgent:
        self.owners.append(owner.id)
        return self.agent


class FlakyAgents(StaticAgents):
    """Fails like an account without an API key for its first ``failures`` calls."""

    def __init__(self, agent: StepAgent, failures: int = 1) -> None:
        super().__init__(agent)
        self.failures = failures

    def __call__(self, session: Session, owner: User) -> StepAgent:
        if self.failures > 0:
            self.failures -= 1
            raise ProviderNotConfigured("No API key is set for openrouter.")
        return super().__call__(session, owner)


class BrokenAgents(StaticAgents):
    """Hits a bug (not a domain error) for the owners listed in ``broken``."""

    def __init__(self, agent: StepAgent, broken: set[int]) -> None:
        super().__init__(agent)
        self.broken = broken

    def __call__(self, session: Session, owner: User) -> StepAgent:
        if owner.id in self.broken:
            raise RuntimeError("a bug")
        return super().__call__(session, owner)


def run_service(app: FastAPI) -> RunService:
    """Runs execute inline, inside ``Scheduler.tick``, so a test sees them finished."""
    return RunService(app.state.database, InlineRunExecutor(), max_parallel_steps=2)


def scheduler(app: FastAPI, agents: StaticAgents, clock: Clock) -> Scheduler:
    return Scheduler(app.state.database, run_service(app), agents, clock)


def access(session: Session, user: User, now: datetime = NOW) -> ScheduleAccess:
    return ScheduleAccess(session, user, 20, now)


def new_schedule(
    session: Session, user: User, pipeline_id: int, timing: Timing = DAILY_AT_NINE
) -> ScheduleView:
    """A schedule of the pipeline, running ``"go"``, created at ``NOW``."""
    return create(access(session, user), ScheduleDraft(pipeline_id, timing, RunStart("go")))


def stored(app: FastAPI, schedule_id: int) -> Schedule:
    """The schedule as the database holds it now (a fresh session, so never stale)."""
    with app.state.database.session() as fresh:
        row = fresh.get(Schedule, schedule_id)
    assert row is not None
    return row


def runs_of(session: Session) -> list[Run]:
    """Every run saved, oldest first, read afresh."""
    session.expire_all()
    return list(session.query(Run).order_by(Run.id))


# --- the HTTP tests -------------------------------------------------------------------


def body(pipeline: Pipeline, **fields: Any) -> dict[str, Any]:
    """A valid POST /api/schedules body (daily at 09:00 in Paris, running "go")."""
    return {
        "pipeline_id": pipeline.id,
        "frequency": "daily",
        "time": "09:00",
        "timezone": PARIS,
        "input": "go",
        **fields,
    }


def create_schedule(client: TestClient, pipeline: Pipeline, **fields: Any) -> dict[str, Any]:
    response = client.post("/api/schedules", json=body(pipeline, **fields))
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def listing(client: TestClient, **params: Any) -> list[dict[str, Any]]:
    response = client.get("/api/schedules", params=params)
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()
    return items
