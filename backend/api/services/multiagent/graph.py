"""Build and execute one LangGraph workflow from a saved pipeline.

The graph owns stage ordering, fan-out/join and the review loops that send a
stage's work back. Agent implementations own model and tool behavior behind the
StepAgent port (Strategy + Adapter, AGENTS.md §7); whoever follows a run listens
through the StepObserver port (Observer).

``nodes`` holds what each node does, ``loops`` the review loops, ``conditions``
and ``reviews`` the pure rules they apply.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import date
from itertools import groupby
from operator import attrgetter
from time import perf_counter

from langgraph.graph import END, START, StateGraph

from api.exceptions import DomainError
from api.services.agent_prompts import TeamMember, TeamView
from api.services.multiagent.contracts import (
    PipelineSpec,
    RunControl,
    RunInputs,
    RunResult,
    StepAgent,
    StepResult,
    StepSpec,
)
from api.services.multiagent.loops import (
    LoopWays,
    ReviewLoop,
    add_loop,
    find_loops,
    initial_loops,
    loop_covering,
    recursion_limit,
)
from api.services.multiagent.nodes import (
    RunNodes,
    agent_node,
    agent_node_name,
    join_node,
    join_node_name,
)
from api.services.multiagent.state import GraphState
from api.services.prompts import merge_stage_outputs

logger = logging.getLogger(__name__)


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


def _build_graph(
    stages: list[list[StepSpec]], run: RunNodes, loops: list[ReviewLoop]
) -> StateGraph:
    builder = StateGraph(GraphState)
    heads: list[list[str]] = []
    for position, stage in enumerate(stages):
        loop = loop_covering(loops, position)
        for step in stage:
            builder.add_node(agent_node_name(step), agent_node(step, position, run, loop))
        names = [agent_node_name(step) for step in stage]
        join = join_node_name(position)
        builder.add_node(join, join_node(stage, position))
        # A list edge is a barrier: the join waits for every agent of the stage.
        builder.add_edge(names, join)
        heads.append(names)
    _wire_stages(builder, heads, loops)
    return builder


def _wire_stages(builder: StateGraph, heads: list[list[str]], loops: list[ReviewLoop]) -> None:
    """Chain the stages: each join leads to the next stage's agents (or the end);
    the join of a reviewer's stage leads either there or back, by its verdict."""
    for name in heads[0]:
        builder.add_edge(START, name)
    reviewed_at = {loop.last: loop for loop in loops}
    for position in range(len(heads)):
        join = join_node_name(position)
        forward = heads[position + 1] if position + 1 < len(heads) else [END]
        loop = reviewed_at.get(position)
        if loop is not None:
            add_loop(builder, loop, LoopWays(join, heads[loop.first], forward))
            continue
        for target in forward:
            builder.add_edge(join, target)


def _results(steps: list[StepSpec], newest: dict[int, StepResult]) -> list[StepResult]:
    """Every step's newest result, in execution order; a skipped step is never an output."""
    outputs = output_orders(steps)
    ordered = sorted(steps, key=attrgetter("stage", "order"))
    return [_marked(newest[step.order], step.order in outputs) for step in ordered]


def _marked(result: StepResult, is_output: bool) -> StepResult:
    return replace(result, is_output=is_output and not result.skipped)


def _deliverables(results: list[StepResult]) -> str:
    """The run's result: its output steps' work, joined as a stage's would be; empty
    when none wrote anything. A final reviewer's verdict is not part of it."""
    done = [(result.step_order, result.output) for result in results if result.is_output]
    return merge_stage_outputs([item for item in done if item[1].strip()]) if done else ""


def team_view(pipeline: PipelineSpec, inputs: RunInputs, today: date | None) -> TeamView:
    """What every agent of a run is told about it (``agent_prompts.team_brief``): the
    team in the order it works, the day, and the values the person gave, or their text
    when the pipeline takes no named inputs."""
    ordered = sorted(pipeline.steps, key=attrgetter("stage", "order"))
    members = tuple(TeamMember(step.order, step.stage, step.role, step.title) for step in ordered)
    labels = {field.name: field.display_label for field in pipeline.inputs}
    given = [(labels.get(name, name), value) for name, value in inputs.values.items()]
    if not given and inputs.text.strip():
        given = [("Their request", inputs.text)]
    return TeamView(pipeline.name, members, tuple(item for item in given if item[1].strip()), today)


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
        control = control or RunControl()
        stages = _group_by_stage(steps)
        loops = find_loops(stages)
        team = team_view(pipeline, inputs, control.today)
        graph = _build_graph(stages, RunNodes(agent, control, team), loops).compile()
        started = perf_counter()
        try:
            state = await graph.ainvoke(
                {
                    "current_input": inputs.text,
                    "values": dict(inputs.values),
                    "results": {},
                    "stage_inputs": {0: inputs.text},
                    "loops": initial_loops(loops, control),
                },
                config={
                    "max_concurrency": self._max_parallel_steps,
                    "recursion_limit": recursion_limit(len(stages), loops),
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
        results = _results(steps, state["results"])
        logger.info(
            "pipeline.run pipeline_id=%s stages=%s steps=%s loops=%s duration_ms=%.0f",
            pipeline.pipeline_id,
            len(stages),
            len(results),
            len(loops),
            (perf_counter() - started) * 1000,
        )
        return RunResult(pipeline.name, _deliverables(results) or state["current_input"], results)
