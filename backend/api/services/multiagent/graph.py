"""Build and execute one LangGraph workflow from a saved pipeline.

The graph owns stage ordering and fan-out/join. Agent implementations own model
and tool behavior behind the StepAgent port (Strategy + Adapter, AGENTS.md §7).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
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
    RunResult,
    StepAgent,
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
    results: Annotated[dict[int, StepResult], _merge_results]


class _GraphUpdate(TypedDict, total=False):
    current_input: str
    results: dict[int, StepResult]


def _group_by_stage(steps: list[StepSpec]) -> list[list[StepSpec]]:
    ordered = sorted(steps, key=attrgetter("stage", "order"))
    return [list(group) for _, group in groupby(ordered, key=attrgetter("stage"))]


def _output_orders(steps: list[StepSpec]) -> set[int]:
    marked = {step.order for step in steps if step.is_output}
    if marked:
        return marked
    last_stage = max(step.stage for step in steps)
    return {step.order for step in steps if step.stage == last_stage}


def _agent_node(step: StepSpec, agent: StepAgent) -> Runnable[_GraphState, _GraphUpdate]:
    async def execute(state: _GraphState) -> _GraphUpdate:
        stage_input = state["current_input"]
        task = AgentTask(
            prompt=step_prompt(step.prompt, stage_input),
            model=step.model,
            role=step.role,
            allowed_tools=list(step.allowed_tools) if step.allowed_tools is not None else None,
        )
        try:
            outcome = await agent.execute(task)
        except llm_exceptions.LLMError as cause:
            raise as_domain_error(cause) from cause
        result = StepResult(
            step_order=step.order,
            stage=step.stage,
            title=step.title,
            model=step.model,
            input_used=stage_input,
            output=outcome.output,
            tool_calls=outcome.tool_calls,
        )
        return {"results": {step.order: result}}

    return RunnableLambda(execute)


def _join_node(steps: list[StepSpec]) -> Runnable[_GraphState, _GraphUpdate]:
    def join(state: _GraphState) -> _GraphUpdate:
        outputs = [(step.order, state["results"][step.order].output) for step in steps]
        return {"current_input": merge_stage_outputs(outputs)}

    return RunnableLambda(join)


def _build_graph(stages: list[list[StepSpec]], agent: StepAgent) -> StateGraph:
    builder = StateGraph(_GraphState)
    previous = START
    for index, stage in enumerate(stages):
        agents: list[str] = []
        for step in stage:
            name = f"agent_{step.stage}_{step.order}"
            builder.add_node(name, _agent_node(step, agent))
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

    def run(self, pipeline: PipelineSpec, agent: StepAgent, initial_input: str) -> RunResult:
        """Bridge the synchronous API and native tools to the async graph."""
        return asyncio.run(self.arun(pipeline, agent, initial_input))

    async def arun(self, pipeline: PipelineSpec, agent: StepAgent, initial_input: str) -> RunResult:
        steps = list(pipeline.steps)
        if not steps:
            return RunResult(pipeline.name, initial_input, [])
        stages = _group_by_stage(steps)
        graph = _build_graph(stages, agent).compile()
        started = perf_counter()
        try:
            state = await graph.ainvoke(
                {"current_input": initial_input, "results": {}},
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
        outputs = _output_orders(steps)
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
