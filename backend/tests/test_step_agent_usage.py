"""A pipeline step's agent reports what its model calls used, and obeys its meter."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool, tool

from api.exceptions import BudgetExceeded
from api.models import User
from api.services.agent_runtime import AgentLimits, AgentToolset
from api.services.agent_types import AgentTask
from api.services.llm import LLMProfile, model_info
from api.services.mcp import MCPConnections
from api.services.multiagent.step_agent import (
    LangGraphStepAgent,
    PipelineAgentGenerator,
    StepAgentDependencies,
    StepServices,
)
from api.services.run_budget import RunBudget, RunMeter
from llm.catalog import ModelInfo
from llm.usage import TokenUsage
from tests.conftest import TEST_SETTINGS

PRICED = ModelInfo(
    "test", "vendor/priced", input_price_per_million=1.0, output_price_per_million=2.0
)
LIMITS = AgentLimits(timeout_seconds=5.0, recursion_limit=9, mcp_timeout_seconds=1.0)


@tool
def increment(number: int) -> int:
    """Add one to a number."""
    return number + 1


def answer(text: str, tokens: tuple[int, int], **extra: Any) -> AIMessage:
    usage = {"input_tokens": tokens[0], "output_tokens": tokens[1], "total_tokens": sum(tokens)}
    return AIMessage(content=text, usage_metadata=usage, **extra)  # type: ignore[arg-type]


def loop_model() -> FakeMessagesListChatModel:
    """Call 1 asks for the tool; call 2 answers. No provider reports a cost."""
    return FakeMessagesListChatModel(
        responses=[
            answer(
                "",
                (1000, 100),
                tool_calls=[{"name": "increment", "args": {"number": 2}, "id": "call-1"}],
            ),
            answer("Result is 3", (1500, 400)),
        ]
    )


def toolset(*native: BaseTool) -> AgentToolset:
    return AgentToolset(MCPConnections(), list(native))


@pytest.fixture(autouse=True)
def tools_bind_to_the_fake_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(FakeMessagesListChatModel, "bind_tools", lambda self, tools, **kw: self)


@pytest.mark.asyncio
async def test_a_step_reports_the_sum_of_every_model_call_it_made() -> None:
    agent = LangGraphStepAgent(loop_model(), toolset(increment), LIMITS, StepServices(PRICED))

    outcome = await agent.reply(AgentTask("add", "vendor/priced", "", ["increment"]))

    assert outcome.output == "Result is 3"
    assert [call.name for call in outcome.tool_calls] == ["increment"]
    assert (outcome.usage.input_tokens, outcome.usage.output_tokens) == (2500, 500)
    # Nothing was reported, so the catalogue prices it: $1/M in, $2/M out.
    assert outcome.usage.cost_usd == pytest.approx(0.0035)
    assert outcome.usage.cost_complete is True


@pytest.mark.asyncio
async def test_a_step_on_an_unpriced_model_keeps_its_tokens_and_an_unknown_cost() -> None:
    agent = LangGraphStepAgent(loop_model(), toolset(increment), LIMITS)

    outcome = await agent.reply(AgentTask("add", "vendor/unknown", "", ["increment"]))

    assert outcome.usage.total_tokens == 3000
    assert outcome.usage.cost_usd is None
    assert outcome.usage.cost_complete is False


@pytest.mark.asyncio
async def test_each_model_call_reaches_the_tasks_meter_as_it_finishes() -> None:
    saved: list[tuple[int, TokenUsage]] = []
    meter = RunMeter(RunBudget(), TokenUsage(), lambda order, usage: saved.append((order, usage)))
    agent = LangGraphStepAgent(loop_model(), toolset(increment), LIMITS, StepServices(PRICED))
    task = AgentTask("add", "vendor/priced", "", ["increment"], meter=meter.for_step(4))

    outcome = await agent.reply(task)

    assert [order for order, _ in saved] == [4, 4]
    assert [usage.total_tokens for _, usage in saved] == [1100, 1900]
    assert meter.spent == outcome.usage


@pytest.mark.asyncio
async def test_a_run_that_reached_its_limit_refuses_the_steps_next_call() -> None:
    saved: list[tuple[int, TokenUsage]] = []
    meter = RunMeter(
        RunBudget(max_tokens=1000), TokenUsage(), lambda order, usage: saved.append((order, usage))
    )
    agent = LangGraphStepAgent(loop_model(), toolset(increment), LIMITS, StepServices(PRICED))
    task = AgentTask("add", "vendor/priced", "", ["increment"], meter=meter.for_step(1))

    with pytest.raises(BudgetExceeded) as raised:
        await agent.reply(task)

    assert raised.value.code == "budget_exceeded"
    assert raised.value.detail == (
        "This run stopped at 1,100 tokens because it reached its 1,000-token limit."
    )
    # The first call finished and is counted; the second never went out.
    assert [usage.total_tokens for _, usage in saved] == [1100]


def test_a_models_prices_come_from_the_catalogue_of_the_users_provider() -> None:
    together = LLMProfile("togetherai", "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8")
    openrouter = LLMProfile("openrouter", "deepseek/deepseek-v4-flash")

    sourced = model_info(together, "openai/gpt-oss-120b")
    assert sourced is not None and sourced.price(1_000_000, 1_000_000) == pytest.approx(0.75)
    assert model_info(together, "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8") is not None
    # The same id on another provider is another catalogue entry, with no price.
    other = model_info(openrouter, "openai/gpt-oss-120b")
    assert other is not None and other.price(1, 1) is None
    free = model_info(openrouter, "nvidia/nemotron-3-super-120b-a12b:free")
    assert free is not None and free.price(10_000, 10_000) == 0.0
    assert model_info(together, "no/such-model") is None
    assert model_info(LLMProfile("nowhere", "x"), "openai/gpt-oss-120b") is None


@pytest.mark.asyncio
async def test_the_generator_prices_a_step_from_its_models_catalogue_entry(
    app: FastAPI, user: User
) -> None:
    model = FakeMessagesListChatModel(responses=[answer("done", (2_000_000, 1_000_000))])
    generator = PipelineAgentGenerator(
        app.state.database,
        user,
        LLMProfile("openrouter", "vendor/priced"),
        StepAgentDependencies(
            model_factory=lambda model_id: model,
            settings=TEST_SETTINGS,
            model_info=lambda model_id: PRICED if model_id == "vendor/priced" else None,
        ),
    )

    priced = await generator.execute(AgentTask("go", "vendor/priced", "", []))

    assert priced.usage.cost_usd == pytest.approx(4.0)
    model.i = 0
    unpriced = await generator.execute(AgentTask("go", "vendor/other", "", []))
    assert unpriced.usage.total_tokens == 3_000_000
    assert unpriced.usage.cost_usd is None
