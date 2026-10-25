"""A run's spending limits: when one is reached, what it says, and a meter that
steps running side by side can share without losing or doubling a call."""

from __future__ import annotations

import threading

import pytest

from api.exceptions import BudgetExceeded
from api.services.run_budget import (
    NO_BUDGET,
    RunBudget,
    RunMeter,
    default_budget,
    ensure_room,
    format_usd,
    limit_reached,
)
from config.settings import Settings
from llm.usage import NO_USAGE, TokenUsage


class Saved:
    """What a run meter saved to the steps: (step order, usage) per call."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, TokenUsage]] = []
        self._lock = threading.Lock()

    def __call__(self, step_order: int, usage: TokenUsage) -> None:
        with self._lock:
            self.calls.append((step_order, usage))

    def total(self) -> TokenUsage:
        return sum((usage for _, usage in self.calls), NO_USAGE)


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (0, "$0.00"),
        (0.00001, "<$0.0001"),
        (0.0001, "$0.0001"),
        (0.0123, "$0.0123"),
        (0.0999, "$0.0999"),
        (0.1, "$0.10"),
        (0.52, "$0.52"),
        (12, "$12.00"),
        (1234.5, "$1,234.50"),
    ],
)
def test_money_reads_the_same_in_every_message(value: float, text: str) -> None:
    assert format_usd(value) == text


def test_no_limit_is_never_reached() -> None:
    assert limit_reached(NO_BUDGET, TokenUsage.of(10**9, 10**9, 10**6)) is None


def test_a_cost_limit_is_reached_exactly_at_the_limit() -> None:
    budget = RunBudget(max_cost_usd=0.5)

    assert limit_reached(budget, TokenUsage.of(1, 1, 0.4999)) is None
    reached = limit_reached(budget, TokenUsage.of(1, 1, 0.5))
    assert reached is not None
    assert (reached.used, reached.limit) == ("$0.50", "$0.50")


def test_a_token_limit_counts_tokens_in_and_out() -> None:
    budget = RunBudget(max_tokens=1000)

    assert limit_reached(budget, TokenUsage.of(600, 399, None)) is None
    reached = limit_reached(budget, TokenUsage.of(600, 400, None))
    assert reached is not None
    assert (reached.used, reached.limit) == ("1,000 tokens", "1,000-token")


def test_a_cost_limit_cannot_stop_calls_whose_cost_is_unknown_but_a_token_limit_can() -> None:
    unknown = TokenUsage.of(5_000_000, 5_000_000, None)

    assert limit_reached(RunBudget(max_cost_usd=0.01), unknown) is None
    assert limit_reached(RunBudget(max_cost_usd=0.01, max_tokens=1_000_000), unknown) is not None


def test_when_both_limits_are_reached_the_cost_one_is_named() -> None:
    reached = limit_reached(RunBudget(0.1, 10), TokenUsage.of(100, 100, 0.2))

    assert reached is not None and reached.limit == "$0.10"


def test_a_limit_left_unset_takes_the_fallbacks() -> None:
    fallback = RunBudget(max_cost_usd=1.0, max_tokens=5000)

    assert RunBudget().or_else(fallback) == fallback
    assert RunBudget(max_cost_usd=0.25).or_else(fallback) == RunBudget(0.25, 5000)
    assert RunBudget(max_tokens=10).or_else(fallback) == RunBudget(1.0, 10)
    assert RunBudget(0.25, 10).or_else(fallback) == RunBudget(0.25, 10)
    assert NO_BUDGET.or_else(NO_BUDGET) == NO_BUDGET


def test_the_servers_default_limit_comes_from_settings() -> None:
    assert default_budget(Settings(_env_file=None)) == NO_BUDGET  # type: ignore[call-arg]
    configured = Settings(_env_file=None, run_default_max_cost_usd=2.5)  # type: ignore[call-arg]
    assert default_budget(configured) == RunBudget(max_cost_usd=2.5)


def test_the_meter_lets_calls_through_until_the_limit_is_reached() -> None:
    meter = RunMeter(RunBudget(max_cost_usd=0.5), NO_USAGE, Saved())
    step = meter.for_step(1)

    step.before_call()
    step.after_call(TokenUsage.of(100, 100, 0.49))
    step.before_call()
    step.after_call(TokenUsage.of(100, 100, 0.03))

    with pytest.raises(BudgetExceeded) as raised:
        step.before_call()
    assert raised.value.code == "budget_exceeded"
    assert raised.value.status_code == 409
    assert raised.value.detail == "This run stopped at $0.52 because it reached its $0.50 limit."


def test_a_resumed_run_starts_from_what_it_already_spent() -> None:
    spent = TokenUsage.of(1000, 1000, 0.45)
    meter = RunMeter(RunBudget(max_cost_usd=0.5), spent, Saved())

    meter.for_step(2).before_call()
    meter.for_step(2).after_call(TokenUsage.of(10, 10, 0.06))

    with pytest.raises(BudgetExceeded, match=r"stopped at \$0\.51"):
        meter.for_step(2).before_call()
    assert meter.spent.total_tokens == 2020


def test_a_call_that_used_nothing_is_not_saved() -> None:
    saved = Saved()
    meter = RunMeter(NO_BUDGET, NO_USAGE, saved)

    meter.for_step(1).after_call(NO_USAGE)

    assert saved.calls == []
    assert meter.spent == NO_USAGE


def test_steps_running_side_by_side_lose_and_double_nothing() -> None:
    saved = Saved()
    meter = RunMeter(NO_BUDGET, NO_USAGE, saved)
    threads_count, calls_each = 8, 250
    start = threading.Barrier(threads_count)

    def work(step_order: int) -> None:
        step = meter.for_step(step_order)
        start.wait()
        for _ in range(calls_each):
            step.before_call()
            step.after_call(TokenUsage.of(3, 2, 0.001))

    threads = [threading.Thread(target=work, args=(order,)) for order in range(threads_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    calls = threads_count * calls_each
    assert meter.spent.input_tokens == 3 * calls
    assert meter.spent.output_tokens == 2 * calls
    assert meter.spent.cost_usd == pytest.approx(0.001 * calls)
    # Every call was saved to its own step, once.
    assert len(saved.calls) == calls
    written = saved.total()
    assert (written.input_tokens, written.output_tokens) == (3 * calls, 2 * calls)
    assert written.cost_usd == pytest.approx(0.001 * calls)
    for order in range(threads_count):
        assert sum(1 for step, _ in saved.calls if step == order) == calls_each


def test_a_run_over_a_limit_cannot_resume_under_it() -> None:
    spent = TokenUsage.of(1000, 1000, 0.52)

    ensure_room(RunBudget(max_cost_usd=1.0), spent)
    ensure_room(NO_BUDGET, spent)
    with pytest.raises(BudgetExceeded) as raised:
        ensure_room(RunBudget(max_cost_usd=0.5), spent)

    assert raised.value.detail == (
        "This run already reached its $0.50 limit (it used $0.52). Raise the limit to resume it."
    )
