"""Build and execute one LangGraph workflow from a saved pipeline.

The graph owns stage ordering and fan-out/join. Agent implementations own model
and tool behavior behind the StepAgent port (Strategy + Adapter, AGENTS.md §7);
whoever follows a run listens through the StepObserver port (Observer).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from itertools import groupby
from operator import attrgetter
from time import perf_counter
from typing import Annotated, TypedDict

from langchain_core.runnables import Runnable, RunnableLambda
from langgraph.graph import END, START, StateGraph

from api.exceptions import DomainError
from api.services.agent_types import AgentTask
from api.services.errors import as_domain_error
from api.services.multiagent.contracts import (
    PipelineSpec,
    RunControl,
    RunInputs,
    RunResult,
    StepAgent,
    StepEvent,
    StepEventKind,
    StepResult,
    StepSpec,
)
from api.services.prompts import merge_stage_outputs, step_prompt
from llm import exceptions as llm_exceptions

logger = logging.getLogger(__name__)


def _merge_results(
    existing: dict[int, StepResult], update: dict[int, StepResult]
) -> dict[int, StepResult]:
    return {**existing, **update}


class _GraphState(TypedDict):
    current_input: str
    #: The run's named inputs; set once, never written by a node.
    values: dict[str, str]
    results: Annotated[dict[int, StepResult], _merge_results]


class _GraphUpdate(TypedDict, total=False):
    current_input: str
    results: dict[int, StepResult]


def _group_by_stage(steps: list[StepSpec]) -> list[list[StepSpec]]:
    ordered = sorted(steps, key=attrgetter("stage", "order"))
    return [list(group) for _, group in groupby(ordered, key=attrgetter("stage"))]


def output_orders(steps: list[StepSpec] | tuple[StepSpec, ...]) -> set[int]:
    """The steps whose results are the pipeline's outputs: the marked ones, or
    else the last stage's."""
    marked = {step.order for step in steps if step.is_output}
    if marked:
        return marked
    last_stage = max(step.stage for step in steps)
    return {step.order for step in steps if step.stage == last_stage}


@dataclass(frozen=True)
class _Nodes:
    """What every agent node of one run shares."""

    agent: StepAgent
    control: RunControl


async def _run_step(step: StepSpec, task: AgentTask, stage_input: str, nodes: _Nodes) -> StepResult:
    """Execute one step's agent, telling the observer how it goes."""
    notify = nodes.control.observer.on_step_event
    await notify(StepEvent(StepEventKind.STARTED, step, stage_input))
    try:
        outcome = await nodes.agent.execute(task)
    except asyncio.CancelledError:
        # The run was stopped, or a parallel step failed and LangGraph cancelled this one.
        await notify(StepEvent(StepEventKind.CANCELLED, step, stage_input))
        raise
    except llm_exceptions.LLMError as cause:
        error = as_domain_error(cause)
        await notify(StepEvent(StepEventKind.FAILED, step, stage_input, error=error))
        raise error from cause
    except DomainError as error:
        await notify(StepEvent(StepEventKind.FAILED, step, stage_input, error=error))
        raise
    result = StepResult(
        step_order=step.order,
        stage=step.stage,
        title=step.title,
        model=step.model,
        input_used=stage_input,
        output=outcome.output,
        tool_calls=outcome.tool_calls,
    )
    await notify(StepEvent(StepEventKind.SUCCEEDED, step, stage_input, result=result))
    return result


def _agent_node(
    step: StepSpec, nodes: _Nodes, first_stage: bool
) -> Runnable[_GraphState, _GraphUpdate]:
    async def execute(state: _GraphState) -> _GraphUpdate:
        saved = nodes.control.completed.get(step.order)
        if saved is not None:
            # An earlier attempt of this run already produced it.
            return {"results": {step.order: saved}}
        stage_input = state["current_input"]
        task = AgentTask(
            prompt=step_prompt(step.prompt, stage_input, state["values"], first_stage=first_stage),
            model=step.model,
            role=step.role,
            allowed_tools=list(step.allowed_tools) if step.allowed_tools is not None else None,
            expected_output=step.expected_output,
        )
        return {"results": {step.order: await _run_step(step, task, stage_input, nodes)}}

    return RunnableLambda(execute)


def _join_node(steps: list[StepSpec]) -> Runnable[_GraphState, _GraphUpdate]:
    def join(state: _GraphState) -> _GraphUpdate:
        outputs = [(step.order, state["results"][step.order].output) for step in steps]
        return {"current_input": merge_stage_outputs(outputs)}

    return RunnableLambda(join)


def _build_graph(stages: list[list[StepSpec]], nodes: _Nodes) -> StateGraph:
    builder = StateGraph(_GraphState)
    previous = START
    for index, stage in enumerate(stages):
        agents: list[str] = []
        for step in stage:
            name = f"agent_{step.stage}_{step.order}"
            builder.add_node(name, _agent_node(step, nodes, first_stage=index == 0))
            builder.add_edge(previous, name)
            agents.append(name)
        join = f"join_{index}"
        builder.add_node(join, _join_node(stage))
        # A list edge is a barrier: the next stage waits for every agent.
        builder.add_edge(agents, join)
        previous = join
    builder.add_edge(previous, END)
    return builder


class GraphPipelineRunner:
    """Graph runner with an injectable agent port and concurrency cap."""

    def __init__(self, max_parallel_steps: int) -> None:
        self._max_parallel_steps = max_parallel_steps

    def run(self, pipeline: PipelineSpec, agent: StepAgent, inputs: RunInputs) -> RunResult:
        """Bridge synchronous callers to the async graph."""
        return asyncio.run(self.arun(pipeline, agent, inputs))

    async def arun(
        self,
        pipeline: PipelineSpec,
        agent: StepAgent,
        inputs: RunInputs,
        control: RunControl | None = None,
    ) -> RunResult:
        """Execute every stage; ``control`` adds an observer and, for a resumed
        run, the results its earlier attempt already produced."""
        steps = list(pipeline.steps)
        if not steps:
            return RunResult(pipeline.name, inputs.text, [])
        stages = _group_by_stage(steps)
        graph = _build_graph(stages, _Nodes(agent, control or RunControl())).compile()
        started = perf_counter()
        try:
            state = await graph.ainvoke(
                {"current_input": inputs.text, "values": dict(inputs.values), "results": {}},
                config={
                    "max_concurrency": self._max_parallel_steps,
                    "recursion_limit": 2 * len(stages) + 2,
                },
            )
        except DomainError as cause:
            logger.warning(
                "pipeline.run_failed pipeline_id=%s code=%s duration_ms=%.0f",
                pipeline.pipeline_id,
                cause.code,
                (perf_counter() - started) * 1000,
            )
            raise
        ordered = sorted(steps, key=attrgetter("stage", "order"))
        outputs = output_orders(steps)
        results = [
            replace(state["results"][step.order], is_output=step.order in outputs)
            for step in ordered
        ]
        logger.info(
            "pipeline.run pipeline_id=%s stages=%s steps=%s duration_ms=%.0f",
            pipeline.pipeline_id,
            len(stages),
            len(results),
            (perf_counter() - started) * 1000,
        )
        return RunResult(pipeline.name, state["current_input"], results)
