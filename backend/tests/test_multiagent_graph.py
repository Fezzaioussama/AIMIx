"""LangGraph pipeline orchestration with replaceable, asynchronous step agents."""

from __future__ import annotations

import asyncio

import pytest

from api.exceptions import ProviderUnavailable
from api.models import Pipeline, PipelineStep
from api.services.agent_types import AgentOutcome, AgentTask, ToolCallTrace
from api.services.multiagent.contracts import PipelineSpec
from api.services.multiagent.graph import GraphPipelineRunner
from api.services.multiagent.mapper import snapshot_pipeline
from api.services.prompts import merge_stage_outputs


def _step(order: int, stage: int) -> PipelineStep:
    return PipelineStep(
        order=order,
        stage=stage,
        title=f"Step {order}",
        role=f"role-{order}",
        allowed_tools=[f"tool-{order}"],
        is_output=False,
        prompt=f"prompt-{order}: {{input}}",
        model=f"model-{order}",
    )


def _pipeline(*steps: PipelineStep) -> PipelineSpec:
    return snapshot_pipeline(Pipeline(name="Graph test", steps=list(steps)))


def _outcome(output: str) -> AgentOutcome:
    return AgentOutcome(output=output, tool_calls=[])


def test_snapshot_copies_step_prompt_and_allowed_tools() -> None:
    step = _step(1, 1)
    snapshot = _pipeline(step)

    selected = step.allowed_tools
    assert selected is not None
    selected.append("added_later")
    step.prompt = "changed later"

    assert snapshot.steps[0].allowed_tools == ("tool-1",)
    assert snapshot.steps[0].prompt == "prompt-1: {input}"


def test_parallel_fan_out_waits_for_both_branches_and_merges_in_step_order() -> None:
    fast_done = asyncio.Event()
    slow_done = asyncio.Event()
    merged = merge_stage_outputs([(1, "slow"), (2, "fast")])

    class Agent:
        async def execute(self, task: AgentTask) -> AgentOutcome:
            if task.role == "role-1":
                await asyncio.wait_for(fast_done.wait(), timeout=2)
                slow_done.set()
                return _outcome("slow")
            if task.role == "role-2":
                fast_done.set()
                return _outcome("fast")
            assert fast_done.is_set() and slow_done.is_set()
            assert task.prompt == f"prompt-3: {merged}"
            return _outcome("combined")

    pipeline = _pipeline(_step(3, 2), _step(2, 1), _step(1, 1))
    result = GraphPipelineRunner(max_parallel_steps=2).run(pipeline, Agent(), "seed")

    assert [item.step_order for item in result.intermediate_results] == [1, 2, 3]
    assert [item.output for item in result.intermediate_results] == ["slow", "fast", "combined"]
    assert [item.input_used for item in result.intermediate_results] == ["seed", "seed", merged]
    assert result.final_output == "combined"


def test_graph_limits_active_agents_to_configured_parallelism() -> None:
    release = asyncio.Event()

    class Agent:
        active = 0
        peak = 0

        async def execute(self, task: AgentTask) -> AgentOutcome:
            self.active += 1
            self.peak = max(self.peak, self.active)
            if self.active == 2:
                release.set()
            await asyncio.wait_for(release.wait(), timeout=2)
            await asyncio.sleep(0.02)
            self.active -= 1
            return _outcome(task.role)

    agent = Agent()
    pipeline = _pipeline(*(_step(order, 1) for order in range(1, 5)))
    result = GraphPipelineRunner(max_parallel_steps=2).run(pipeline, agent, "seed")

    assert agent.peak == 2
    assert [item.step_order for item in result.intermediate_results] == [1, 2, 3, 4]


def test_long_sequential_pipeline_completes_past_default_graph_recursion_limit() -> None:
    class Agent:
        async def execute(self, task: AgentTask) -> AgentOutcome:
            return _outcome(task.role)

    pipeline = _pipeline(*(_step(order, order) for order in range(1, 16)))
    result = GraphPipelineRunner(max_parallel_steps=1).run(pipeline, Agent(), "seed")

    assert [item.step_order for item in result.intermediate_results] == list(range(1, 16))
    assert result.intermediate_results[-1].input_used == "role-14"
    assert result.final_output == "role-15"


def test_failing_branch_prevents_later_stage() -> None:
    visited: list[str] = []

    class Agent:
        async def execute(self, task: AgentTask) -> AgentOutcome:
            visited.append(task.role)
            if task.role == "role-1":
                raise ProviderUnavailable("branch failed")
            return _outcome(task.role)

    pipeline = _pipeline(_step(1, 1), _step(2, 1), _step(3, 2))

    with pytest.raises(ProviderUnavailable, match="branch failed"):
        GraphPipelineRunner(max_parallel_steps=2).run(pipeline, Agent(), "seed")

    assert "role-3" not in visited


def test_each_step_receives_its_own_role_model_and_tool_policy() -> None:
    tasks: list[AgentTask] = []

    class Agent:
        async def execute(self, task: AgentTask) -> AgentOutcome:
            tasks.append(task)
            return AgentOutcome(
                output=task.model,
                tool_calls=[ToolCallTrace(name="lookup", status="success")],
            )

    first = _step(1, 1)
    first.role = "Researcher"
    first.allowed_tools = None
    second = _step(2, 2)
    second.role = "Writer"
    second.allowed_tools = []
    second.is_output = True
    result = GraphPipelineRunner(max_parallel_steps=2).run(
        _pipeline(first, second), Agent(), "seed"
    )

    assert tasks == [
        AgentTask("prompt-1: seed", "model-1", "Researcher", None),
        AgentTask("prompt-2: model-1", "model-2", "Writer", []),
    ]
    assert result.final_output == "model-2"
    assert [item.is_output for item in result.intermediate_results] == [False, True]
    assert all(
        item.tool_calls == [ToolCallTrace("lookup", "success")]
        for item in result.intermediate_results
    )
