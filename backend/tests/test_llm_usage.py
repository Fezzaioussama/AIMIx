"""What model calls use and cost: counted from each answer, priced from the
provider's report or the catalogue, and seen by a meter before and after each call."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from langchain.agents import create_agent
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from langchain_core.tools import tool

from llm.catalog import CATALOGS, ModelInfo
from llm.usage import (
    NO_USAGE,
    TokenUsage,
    UsageCallback,
    call_usage,
    metered,
    response_usage,
    total,
)

#: $1 per million input tokens and $2 per million output tokens: easy sums.
PRICED = ModelInfo(
    "test", "vendor/priced", input_price_per_million=1.0, output_price_per_million=2.0
)
UNPRICED = ModelInfo("test", "vendor/unpriced")


def answer(
    text: str = "ok",
    tokens: tuple[int, int] | None = (1000, 500),
    cost: object | None = None,
    **extra: Any,
) -> AIMessage:
    """A model answer as LangChain hands it over: usage in ``usage_metadata``,
    a provider-reported cost (OpenRouter) in ``response_metadata``."""
    usage = (
        {"input_tokens": tokens[0], "output_tokens": tokens[1], "total_tokens": sum(tokens)}
        if tokens
        else None
    )
    metadata = {} if cost is None else {"cost": cost}
    return AIMessage(content=text, usage_metadata=usage, response_metadata=metadata, **extra)


def test_usage_adds_up_tokens_and_the_costs_that_are_known() -> None:
    first = TokenUsage.of(100, 50, 0.01)
    second = TokenUsage.of(200, 25, 0.02)

    combined = first + second

    assert (combined.input_tokens, combined.output_tokens) == (300, 75)
    assert combined.total_tokens == 375
    assert combined.cost_usd == pytest.approx(0.03)
    assert combined.cost_complete is True
    assert total([first, second]) == combined
    assert total([]) == NO_USAGE


def test_tokens_without_a_known_cost_make_the_total_incomplete_but_still_count() -> None:
    known = TokenUsage.of(100, 50, 0.01)
    unknown = TokenUsage.of(200, 25, None)

    combined = known + unknown

    assert combined.total_tokens == 375
    assert combined.cost_usd == pytest.approx(0.01)
    assert combined.cost_complete is False
    # Nothing used, so nothing is missing: an empty step does not spoil a total.
    assert (known + TokenUsage.of(0, 0, None)).cost_complete is True
    assert total([unknown, unknown]).cost_usd is None


def test_the_providers_reported_cost_is_used_as_it_is() -> None:
    usage = call_usage(answer(cost=0.0042), PRICED)

    assert usage == TokenUsage(1000, 500, 0.0042, True)


def test_a_reported_cost_beats_the_catalogue_even_when_it_is_zero() -> None:
    # A free call reported as free must not be priced from the catalogue.
    assert call_usage(answer(cost=0), PRICED).cost_usd == 0.0
    assert call_usage(answer(cost=0.0), PRICED).cost_usd == 0.0


def test_without_a_reported_cost_the_catalogue_prices_the_tokens() -> None:
    usage = call_usage(answer(tokens=(2_000_000, 1_000_000)), PRICED)

    assert usage.cost_usd == pytest.approx(4.0)
    assert usage.cost_complete is True


def test_without_a_reported_cost_or_a_price_the_cost_is_unknown_but_tokens_count() -> None:
    for model in (UNPRICED, None):
        usage = call_usage(answer(), model)

        assert (usage.input_tokens, usage.output_tokens) == (1000, 500)
        assert usage.cost_usd is None
        assert usage.cost_complete is False


@pytest.mark.parametrize("reported", [-0.5, float("nan"), float("inf"), "0.01", True, [0.01]])
def test_a_reported_cost_that_makes_no_sense_is_ignored(reported: object) -> None:
    assert call_usage(answer(cost=reported), PRICED).cost_usd == pytest.approx(0.002)
    assert call_usage(answer(cost=reported), None).cost_usd is None


def test_an_answer_without_usage_counts_nothing() -> None:
    assert call_usage(answer(tokens=None, cost=0.5), PRICED) == NO_USAGE


def test_a_model_prices_tokens_only_when_both_prices_are_known() -> None:
    half = ModelInfo("test", "vendor/half", input_price_per_million=1.0)

    assert PRICED.price(1_000_000, 1_000_000) == pytest.approx(3.0)
    assert PRICED.price(0, 0) == 0.0
    assert half.price(10, 10) is None
    assert UNPRICED.price(10, 10) is None


def test_every_price_in_the_catalogue_is_complete_and_never_negative() -> None:
    priced = [
        model
        for catalog in CATALOGS.values()
        for model in catalog.all().values()
        if model.price(1, 1) is not None
    ]

    assert priced, "at least the free and the sourced models carry prices"
    for model in priced:
        assert model.input_price_per_million is not None and model.input_price_per_million >= 0
        assert model.output_price_per_million is not None and model.output_price_per_million >= 0
    # Never an invented price: a model is priced on both sides or on neither.
    for catalog in CATALOGS.values():
        for model in catalog.all().values():
            assert (model.input_price_per_million is None) == (
                model.output_price_per_million is None
            )


def generation(*messages: AIMessage) -> list[ChatGeneration]:
    return [ChatGeneration(message=message) for message in messages]


def test_the_choices_of_one_prompt_repeat_its_usage_so_they_count_once() -> None:
    both_choices = generation(answer(cost=0.01), answer("second choice", cost=0.01))

    usage = response_usage(LLMResult(generations=[both_choices]), PRICED)

    assert usage == TokenUsage(1000, 500, 0.01, True)


def test_each_prompt_of_a_batch_counts_its_own_usage() -> None:
    result = LLMResult(generations=[generation(answer(cost=0.01)), generation(answer(cost=0.02))])

    usage = response_usage(result, PRICED)

    assert (usage.total_tokens, usage.cost_usd) == (3000, pytest.approx(0.03))
    assert response_usage(LLMResult(generations=[[]]), PRICED) == NO_USAGE


class RecordingMeter:
    """Sees every call: what was refused before it, and what each one used."""

    def __init__(self, refuse_from_call: int | None = None) -> None:
        self.refuse_from_call = refuse_from_call
        self.events: list[str] = []
        self.usages: list[TokenUsage] = []

    def before_call(self) -> None:
        self.events.append("before")
        if (
            self.refuse_from_call is not None
            and self.events.count("before") >= self.refuse_from_call
        ):
            raise StopAgent("over the limit")

    def after_call(self, usage: TokenUsage) -> None:
        self.events.append("after")
        self.usages.append(usage)


class StopAgent(Exception):
    """What a meter raises to refuse a call."""


@tool
def increment(number: int) -> int:
    """Add one to a number."""
    return number + 1


def looping_model(*, cost: bool) -> FakeMessagesListChatModel:
    """Two model calls: one asks for the tool, the next gives the answer."""
    return FakeMessagesListChatModel(
        responses=[
            answer(
                "",
                tokens=(1000, 100),
                cost=0.001 if cost else None,
                tool_calls=[{"name": "increment", "args": {"number": 2}, "id": "call-1"}],
            ),
            answer("Result is 3", tokens=(1500, 400), cost=0.002 if cost else None),
        ]
    )


@pytest.fixture(autouse=True)
def tools_bind_to_the_fake_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(FakeMessagesListChatModel, "bind_tools", lambda self, tools, **kw: self)


def run_agent(model: Any) -> dict[str, Any]:
    graph = create_agent(model, [increment])
    result: dict[str, Any] = asyncio.run(
        graph.ainvoke({"messages": [{"role": "user", "content": "add"}]})
    )
    return result


def test_every_call_of_a_multi_call_agent_loop_is_counted_and_summed() -> None:
    meter = RecordingMeter()
    callback = UsageCallback(UNPRICED, meter)

    state = run_agent(metered(looping_model(cost=True), callback))

    assert state["messages"][-1].text == "Result is 3"
    assert meter.events == ["before", "after", "before", "after"]
    assert meter.usages == [TokenUsage(1000, 100, 0.001), TokenUsage(1500, 400, 0.002)]
    assert callback.total.input_tokens == 2500
    assert callback.total.output_tokens == 500
    assert callback.total.cost_usd == pytest.approx(0.003)
    assert callback.total.cost_complete is True


def test_the_loop_is_priced_from_the_catalogue_when_nothing_is_reported() -> None:
    callback = UsageCallback(PRICED)

    run_agent(metered(looping_model(cost=False), callback))

    # 2,500 in at $1/M and 500 out at $2/M.
    assert callback.total.cost_usd == pytest.approx(0.0035)


def test_the_loop_has_an_unknown_cost_when_nothing_prices_it() -> None:
    callback = UsageCallback(UNPRICED)

    run_agent(metered(looping_model(cost=False), callback))

    assert callback.total.total_tokens == 3000
    assert callback.total.cost_usd is None
    assert callback.total.cost_complete is False


def test_a_meter_that_refuses_a_call_stops_the_agent_with_its_own_error() -> None:
    meter = RecordingMeter(refuse_from_call=2)
    callback = UsageCallback(UNPRICED, meter)

    with pytest.raises(StopAgent, match="over the limit"):
        run_agent(metered(looping_model(cost=True), callback))

    # The first call finished and was counted; the second never went out.
    assert meter.events == ["before", "after", "before"]
    assert callback.total == TokenUsage(1000, 100, 0.001)


def test_metering_a_model_keeps_its_own_callbacks_and_leaves_the_original_alone() -> None:
    class Mine(BaseCallbackHandler):
        calls = 0

        def on_chat_model_start(self, *args: Any, **kwargs: Any) -> None:
            Mine.calls += 1

    original = looping_model(cost=True)
    original.callbacks = [Mine()]
    callback = UsageCallback(UNPRICED)

    copy = metered(original, callback)
    run_agent(copy)

    assert original.callbacks is not None and len(original.callbacks) == 1
    assert Mine.calls == 2
    assert callback.total.total_tokens == 3000
