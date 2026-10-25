"""Shared by the scheduler and the schedules API tests: a clock the test sets,
fake owner agents, and builders. Nothing here waits for real time."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from fastapi import FastAPI
from sqlalchemy.orm import Session

from api.exceptions import ProviderNotConfigured
from api.models import Schedule, ScheduleFrequency, User
from api.services.multiagent.contracts import StepAgent
from api.services.runs import RunService, RunStart
from api.services.schedules.scheduler import Scheduler
from api.services.schedules.service import ScheduleAccess, ScheduleDraft, ScheduleView, create
from api.services.schedules.timing import Timing
from tests.conftest import InlineRunExecutor

#: A Saturday noon in UTC: 14:00 in Paris, just before the clocks go back there.
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
DAILY_AT_NINE = Timing(ScheduleFrequency.DAILY, "UTC", time(9, 0))
HOURLY_AT_QUARTER_PAST = Timing(ScheduleFrequency.HOURLY, "UTC", time(0, 15))


class Clock:
    """A clock the test sets: pass it to ``Scheduler``, or override ``current_time``."""

    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


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


def access(session: Session, user: User, now: datetime = NOW, limit: int = 20) -> ScheduleAccess:
    return ScheduleAccess(session, user, limit, now)


def new_schedule(
    session: Session,
    user: User,
    pipeline_id: int,
    timing: Timing = DAILY_AT_NINE,
    start: RunStart | None = None,
    now: datetime = NOW,
) -> ScheduleView:
    draft = ScheduleDraft(pipeline_id, timing, start or RunStart("go"))
    return create(access(session, user, now), draft)


def stored(app: FastAPI, schedule_id: int) -> Schedule:
    """The schedule as the database holds it now (a fresh session, so never stale)."""
    with app.state.database.session() as fresh:
        row = fresh.get(Schedule, schedule_id)
    assert row is not None
    return row


def at_utc(moment: datetime | None) -> datetime:
    """A stored time (SQLite hands back naive UTC) as an aware one."""
    assert moment is not None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
