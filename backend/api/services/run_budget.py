"""A run's spending limits, enforced while it executes (AGENTS.md §6).

One ``RunMeter`` is shared by every step of an execution. Each model call's
usage is added to the run's running total under a lock, so parallel steps never
lose or double an update, and is saved to its step at once
(``RunRecorder.record_usage``). Before each call the meter checks the total:
once it has reached a limit, the call is refused with ``BudgetExceeded``, its
step fails with ``budget_exceeded`` and the run stops, failed. A call already
sent is never thrown away: it is counted, and its answer kept.

Limits are a cost (USD) and a number of tokens; None is no limit. A call whose
cost is unknown (a model without a price) counts toward the token limit only.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from api.exceptions import BudgetExceeded
from api.models import Run
from config.settings import Settings
from llm.usage import NO_USAGE, TokenUsage, UsageMeter


@dataclass(frozen=True)
class RunBudget:
    """A run's limits; None is no limit (§7 Value Object)."""

    max_cost_usd: float | None = None
    max_tokens: int | None = None

    def or_else(self, fallback: RunBudget) -> RunBudget:
        """These limits, each one left unset taken from ``fallback``."""
        return RunBudget(
            self.max_cost_usd if self.max_cost_usd is not None else fallback.max_cost_usd,
            self.max_tokens if self.max_tokens is not None else fallback.max_tokens,
        )


NO_BUDGET = RunBudget()


def default_budget(settings: Settings) -> RunBudget:
    """The limit of a run that sets none of its own (RUN_DEFAULT_MAX_COST_USD)."""
    return RunBudget(max_cost_usd=settings.run_default_max_cost_usd)


def run_budget(run: Run) -> RunBudget:
    return RunBudget(run.max_cost_usd, run.max_tokens)


def format_usd(value: float) -> str:
    """'$0.0123' under ten cents, else '$0.52' or '$1,234.50'; '<$0.0001' for dust.
    Mirrors formatCost in frontend/src/features/runs/usageFormat.ts."""
    if value == 0:
        return "$0.00"
    if value < 0.0001:
        return "<$0.0001"
    return f"${value:.4f}" if value < 0.1 else f"${value:,.2f}"


def _tokens(count: float) -> str:
    return f"{int(count):,} tokens"


def _token_limit(count: float) -> str:
    return f"{int(count):,}-token"


@dataclass(frozen=True)
class _Limit:
    """One kind of limit: how much a budget allows, how much was used, in words."""

    allowed: Callable[[RunBudget], float | None]
    used: Callable[[TokenUsage], float | None]
    #: "$0.52", "12,345 tokens": an amount used.
    amount: Callable[[float], str]
    #: "$0.50", "10,000-token": the limit, as in "its $0.50 limit".
    limit: Callable[[float], str]


#: Every kind of limit a run can have (Strategy + Registry, §5 O).
LIMITS: tuple[_Limit, ...] = (
    _Limit(lambda b: b.max_cost_usd, lambda u: u.cost_usd, format_usd, format_usd),
    _Limit(lambda b: b.max_tokens, lambda u: u.total_tokens, _tokens, _token_limit),
)


@dataclass(frozen=True)
class LimitReached:
    """A limit ``spent`` has reached, in words."""

    used: str
    limit: str


def limit_reached(budget: RunBudget, spent: TokenUsage) -> LimitReached | None:
    """The first limit ``spent`` has reached; None while every limit has room."""
    for kind in LIMITS:
        allowed, used = kind.allowed(budget), kind.used(spent)
        if allowed is not None and used is not None and used >= allowed:
            return LimitReached(kind.amount(used), kind.limit(allowed))
    return None


def ensure_room(budget: RunBudget, spent: TokenUsage) -> None:
    """Refuse to resume a run that has already reached one of its limits."""
    reached = limit_reached(budget, spent)
    if reached is not None:
        raise BudgetExceeded(
            f"This run already reached its {reached.limit} limit (it used {reached.used}). "
            "Raise the limit to resume it."
        )


#: Saves one finished call's usage to its step: (step order, usage).
UsageRecorder = Callable[[int, TokenUsage], None]


class RunMeter:
    """The running total of one execution's model calls, shared by its steps."""

    def __init__(self, budget: RunBudget, spent: TokenUsage, record: UsageRecorder) -> None:
        self._budget = budget
        self._spent = spent
        self._record = record
        self._lock = threading.Lock()

    @property
    def spent(self) -> TokenUsage:
        with self._lock:
            return self._spent

    def for_step(self, step_order: int) -> UsageMeter:
        """The meter one step's agent reports its model calls to."""
        return _StepMeter(self, step_order)

    def check(self) -> None:
        """Refuse a new call once the run has reached one of its limits."""
        reached = limit_reached(self._budget, self.spent)
        if reached is not None:
            raise BudgetExceeded(
                f"This run stopped at {reached.used} because it reached its {reached.limit} limit."
            )

    def add(self, step_order: int, usage: TokenUsage) -> None:
        """Count a finished call, and save it to its step."""
        if usage == NO_USAGE:
            return
        with self._lock:
            self._spent += usage
        self._record(step_order, usage)


@dataclass(frozen=True)
class _StepMeter:
    """One step's ``UsageMeter``: its calls count toward the run's total."""

    run: RunMeter
    step_order: int

    def before_call(self) -> None:
        self.run.check()

    def after_call(self, usage: TokenUsage) -> None:
        self.run.add(self.step_order, usage)
