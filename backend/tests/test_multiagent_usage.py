"""The graph carries each step's usage out to whoever listens, and hands every
step the meter its agent reports its model calls to."""

from __future__ import annotations

import asyncio

from api.models import Pipeline, PipelineStep
from api.services.agent_types import AgentOutcome, AgentTask
from api.services.multiagent.contracts import (
    PipelineSpec,
    RunControl,
    RunInputs,
    StepEvent,
    StepEventKind,
)
from api.services.multiagent.graph import GraphPipelineRunner
from api.services.multiagent.mapper import snapshot_pipeline
from llm.usage import NO_USAGE, UNMETERED, TokenUsage, UsageMeter


def pipeline_of(*orders: int) -> PipelineSpec:
    steps = [
        PipelineStep(
            order=order,
            stage=order,
            title=f"Step {order}",
            role=f"role-{order}",
            allowed_tools=None,
            is_output=False,
            prompt="go {input}",
            model="model",
        )
        for order in orders
    ]
    return snapshot_pipeline(Pipeline(name="Usage", steps=steps))


class Recording:
    def __init__(self) -> None:
        self.events: list[StepEvent] = []

    async def on_step_event(self, event: StepEvent) -> None:
        self.events.append(event)


class UsageReportingAgent:
    """Answers with the usage its step number earned: 100 tokens in per step."""

    def __init__(self) -> None:
        self.meters: dict[str, UsageMeter] = {}

    async def execute(self, task: AgentTask) -> AgentOutcome:
        self.meters[task.role] = task.meter
        tokens = int(task.role.removeprefix("role-")) * 100
        return AgentOutcome(task.role, [], TokenUsage.of(tokens, tokens // 2, tokens / 1000))


class SilentMeter:
    def before_call(self) -> None:
        return None

    def after_call(self, usage: TokenUsage) -> None:
        return None


def test_each_steps_usage_reaches_the_observer_and_the_run_result() -> None:
    observer = Recording()

    result = asyncio.run(
        GraphPipelineRunner(2).arun(
            pipeline_of(1, 2),
            UsageReportingAgent(),
            RunInputs("seed"),
            RunControl(observer=observer),
        )
    )

    finished = [event.result for event in observer.events if event.kind == StepEventKind.SUCCEEDED]
    assert [item.usage.input_tokens for item in finished if item is not None] == [100, 200]
    assert [item.usage.cost_usd for item in result.intermediate_results] == [0.1, 0.2]
    started = [event for event in observer.events if event.kind == StepEventKind.STARTED]
    assert all(event.result is None for event in started)


def test_an_agent_that_reports_no_usage_leaves_the_result_with_none() -> None:
    class Silent:
        async def execute(self, task: AgentTask) -> AgentOutcome:
            return AgentOutcome("out", [])

    result = asyncio.run(GraphPipelineRunner(1).arun(pipeline_of(1), Silent(), RunInputs("seed")))

    assert result.intermediate_results[0].usage == NO_USAGE


def test_every_step_gets_the_meter_the_run_made_for_it() -> None:
    handed: dict[int, UsageMeter] = {}

    def meter_for(step_order: int) -> UsageMeter:
        handed[step_order] = SilentMeter()
        return handed[step_order]

    agent = UsageReportingAgent()
    asyncio.run(
        GraphPipelineRunner(2).arun(
            pipeline_of(1, 2), agent, RunInputs("seed"), RunControl(meter=meter_for)
        )
    )

    assert sorted(handed) == [1, 2]
    assert agent.meters["role-1"] is handed[1]
    assert agent.meters["role-2"] is handed[2]


def test_a_run_without_a_meter_hands_steps_one_that_counts_nothing() -> None:
    agent = UsageReportingAgent()

    asyncio.run(GraphPipelineRunner(1).arun(pipeline_of(1), agent, RunInputs("seed")))

    assert agent.meters["role-1"] is UNMETERED
