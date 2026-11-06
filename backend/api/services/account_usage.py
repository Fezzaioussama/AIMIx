"""What one account spends of the server's key, by day, and the bound on it.

An account without a key of its own spends the operator's (ALLOW_SERVER_LLM_KEY).
SERVER_KEY_DAILY_MAX_COST_USD and SERVER_KEY_DAILY_MAX_TOKENS bound what it may
spend per UTC day, runs, chat and the planner together. ``AccountMeter`` hears
every model call made for the account (as a run's ``RunMeter`` does for the run):
it refuses one once the day's allowance is used up (``DailyLimitReached``), and
keeps the calls runs do not record themselves (a chat message's and the planner's
become ``UsageEvent`` rows; a run's are on its steps). An account with its own key
is counted the same way and never bounded. Plain values in and out (AGENTS.md §2).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from api.db import Database
from api.exceptions import DailyLimitReached
from api.models import UsageKind
from api.repositories import usage as repository
from api.repositories.usage import NewUsageEvent
from api.services.llm import LLMProfile
from api.services.run_budget import NO_BUDGET, RunBudget, limit_reached
from api.services.run_recorder import utcnow
from config.settings import Settings, get_settings
from llm.usage import NO_USAGE, UNMETERED, TokenUsage, UsageMeter

Clock = Callable[[], datetime]


def daily_allowance(settings: Settings) -> RunBudget:
    """What an account on the server's key may spend per day (SERVER_KEY_DAILY_MAX_*)."""
    return RunBudget(settings.server_key_daily_max_cost_usd, settings.server_key_daily_max_tokens)


def day_start(now: datetime) -> datetime:
    """Midnight UTC before ``now``: the day's spending starts there."""
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def spent_today(session: Session, user_id: int, now: datetime) -> TokenUsage:
    """The account's runs, chats and planning since midnight UTC, as one usage."""
    return repository.spent_since(session, user_id, day_start(now))


def ensure_room(session: Session, user_id: int, allowance: RunBudget, now: datetime) -> None:
    """Refuse a call once the day's allowance is used up."""
    reached = limit_reached(allowance, spent_today(session, user_id, now))
    if reached is not None:
        raise DailyLimitReached(
            f"Today's allowance of the server's key is used up: {reached.used} of its "
            f"{reached.limit} daily limit. Add your own API key on the Settings page, "
            "or come back after midnight UTC."
        )


@dataclass(frozen=True)
class Calls:
    """Which calls a meter hears: their kind (None for a run's, which its steps
    record), the model they are made on, and the day's allowance of the server's
    key, which applies only to an account without a key of its own."""

    kind: UsageKind | None
    model: str
    allowance: RunBudget = NO_BUDGET


def calls_of(kind: UsageKind | None, model: str) -> Calls:
    """The calls of ``kind`` on ``model``, under the settings' daily allowance."""
    return Calls(kind, model, daily_allowance(get_settings()))


@dataclass(frozen=True)
class AccountMeter:
    """A ``UsageMeter`` for the model calls made for one account."""

    database: Database
    user_id: int
    calls: Calls
    clock: Clock = utcnow

    def before_call(self) -> None:
        if self.calls.allowance == NO_BUDGET:
            return
        with self.database.session() as session:
            ensure_room(session, self.user_id, self.calls.allowance, self.clock())

    def after_call(self, usage: TokenUsage) -> None:
        if self.calls.kind is None or usage == NO_USAGE:
            return
        event = NewUsageEvent(
            self.user_id,
            self.calls.kind,
            self.calls.model,
            usage.input_tokens,
            usage.output_tokens,
            usage.cost_usd,
        )
        with self.database.session() as session:
            repository.record_event(session, event)


def account_meter(
    database: Database, user_id: int, profile: LLMProfile, calls: Calls
) -> UsageMeter:
    """The meter for ``user_id``'s calls: bounded by the day's allowance while they
    spend the server's key (no key of their own), recorded when a run does not.
    A run's calls on the account's own key need nothing: its steps count them."""
    bounded = Calls(calls.kind, calls.model, NO_BUDGET if profile.api_key else calls.allowance)
    if bounded.kind is None and bounded.allowance == NO_BUDGET:
        return UNMETERED
    return AccountMeter(database, user_id, bounded)
