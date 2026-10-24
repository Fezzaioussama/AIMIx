"""LangGraph pipeline orchestration with replaceable, asynchronous step agents."""

from __future__ import annotations

import asyncio

import pytest

from api.exceptions import ProviderUnavailable
from api.models import Pipeline, PipelineStep
from api.services.agent_types import AgentOutcome, AgentTask, ToolCallTrace
from api.services.multiagent.contracts import (
    InputField,
    PipelineSpec,
    RunControl,
    RunInputs,
    StepEvent,
    StepEventKind,
    StepResult,
)
from api.services.multiagent.graph import GraphPipelineRunner
from api.services.multiagent.mapper import snapshot_pipeline, spec_from_json, spec_to_json
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


def test_snapshot_copies_named_inputs_and_expected_output() -> None:
    step = _step(1, 1)
    step.expected_output = "Three bullet points"
    saved = Pipeline(
        name="Graph test",
        inputs=[{"name": "topic", "label": "Topic", "description": "What to cover"}],
        steps=[step],
    )

    snapshot = snapshot_pipeline(saved)

    assert snapshot.inputs == (InputField("topic", "Topic", "What to cover"),)
    assert snapshot.steps[0].expected_output == "Three bullet points"


def test_named_inputs_reach_later_stages_and_expected_output_reaches_the_agent() -> None:
    tasks: list[AgentTask] = []

    class Agent:
        async def execute(self, task: AgentTask) -> AgentOutcome:
            tasks.append(task)
            return _outcome(f"out-{task.role}")

    research = _step(1, 1)
    research.prompt = "Research {topic}"
    draft = _step(2, 2)
    draft.prompt = "Write for {audience} about {topic}"
    draft.expected_output = "One tweet"
    inputs = RunInputs("labelled inputs", {"topic": "bees", "audience": "kids"})

    result = GraphPipelineRunner(max_parallel_steps=2).run(
        _pipeline(research, draft), Agent(), inputs
    )

    # The first stage placed a named input, so its input is not appended again;
    # the later stage did not place {input}, so the previous output is.
    assert [task.prompt for task in tasks] == [
        "Research bees",
        "Write for kids about bees\n\nInput: out-role-1",
    ]
    assert [task.expected_output for task in tasks] == ["", "One tweet"]
    assert result.intermediate_results[0].input_used == "labelled inputs"


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
    result = GraphPipelineRunner(max_parallel_steps=2).run(pipeline, Agent(), RunInputs("seed"))

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
    result = GraphPipelineRunner(max_parallel_steps=2).run(pipeline, agent, RunInputs("seed"))

    assert agent.peak == 2
    assert [item.step_order for item in result.intermediate_results] == [1, 2, 3, 4]


def test_long_sequential_pipeline_completes_past_default_graph_recursion_limit() -> None:
    class Agent:
        async def execute(self, task: AgentTask) -> AgentOutcome:
            return _outcome(task.role)

    pipeline = _pipeline(*(_step(order, order) for order in range(1, 16)))
    result = GraphPipelineRunner(max_parallel_steps=1).run(pipeline, Agent(), RunInputs("seed"))

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
        GraphPipelineRunner(max_parallel_steps=2).run(pipeline, Agent(), RunInputs("seed"))

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
        _pipeline(first, second), Agent(), RunInputs("seed")
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


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[StepEvent] = []

    async def on_step_event(self, event: StepEvent) -> None:
        self.events.append(event)

    def seen(self) -> list[tuple[StepEventKind, int]]:
        return [(event.kind, event.step.order) for event in self.events]


class EchoRoleAgent:
    def __init__(self) -> None:
        self.roles: list[str] = []

    async def execute(self, task: AgentTask) -> AgentOutcome:
        self.roles.append(task.role)
        return _outcome(f"out-{task.role}")


def test_the_observer_hears_each_step_start_and_finish_in_order() -> None:
    observer = RecordingObserver()

    asyncio.run(
        GraphPipelineRunner(max_parallel_steps=2).arun(
            _pipeline(_step(1, 1), _step(2, 2)),
            EchoRoleAgent(),
            RunInputs("seed"),
            RunControl(observer=observer),
        )
    )

    started, succeeded = StepEventKind.STARTED, StepEventKind.SUCCEEDED
    assert observer.seen() == [(started, 1), (succeeded, 1), (started, 2), (succeeded, 2)]
    assert observer.events[0].input_used == "seed"
    finished = observer.events[3].result
    assert finished is not None and finished.output == "out-role-2"


def test_the_observer_hears_a_failure_and_the_cancelled_parallel_step() -> None:
    observer = RecordingObserver()

    class Agent:
        async def execute(self, task: AgentTask) -> AgentOutcome:
            if task.role == "role-1":
                await asyncio.sleep(0.05)
                raise ProviderUnavailable("branch failed")
            await asyncio.sleep(5)
            return _outcome(task.role)

    with pytest.raises(ProviderUnavailable):
        asyncio.run(
            GraphPipelineRunner(max_parallel_steps=2).arun(
                _pipeline(_step(1, 1), _step(2, 1)),
                Agent(),
                RunInputs("seed"),
                RunControl(observer=observer),
            )
        )

    finished = {event.step.order: event for event in observer.events[2:]}
    assert finished[1].kind == StepEventKind.FAILED
    assert finished[1].error is not None and finished[1].error.code == "provider_unavailable"
    assert finished[2].kind == StepEventKind.CANCELLED


def test_completed_steps_are_reused_without_running_their_agent() -> None:
    observer = RecordingObserver()
    agent = EchoRoleAgent()
    saved = StepResult(1, 1, "Step 1", "model-1", "seed", "saved output")

    result = asyncio.run(
        GraphPipelineRunner(max_parallel_steps=2).arun(
            _pipeline(_step(1, 1), _step(2, 2)),
            agent,
            RunInputs("seed"),
            RunControl(observer=observer, completed={1: saved}),
        )
    )

    assert agent.roles == ["role-2"]
    assert observer.seen() == [(StepEventKind.STARTED, 2), (StepEventKind.SUCCEEDED, 2)]
    assert observer.events[0].input_used == "saved output"
    assert [item.output for item in result.intermediate_results] == ["saved output", "out-role-2"]


def test_a_stored_snapshot_rebuilds_the_same_pipeline() -> None:
    step = _step(1, 1)
    step.expected_output = "A list"
    spec = snapshot_pipeline(
        Pipeline(
            id=4,
            name="Stored",
            inputs=[{"name": "topic", "label": "Topic", "description": ""}],
            steps=[step, _step(2, 2)],
        )
    )

    assert spec_from_json(4, spec_to_json(spec)) == spec
