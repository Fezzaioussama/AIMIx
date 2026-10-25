"""The nodes of the pipeline graph: an agent node per step and a join per stage.

An agent node decides, for its step, whether it runs now: a result an earlier
attempt of the run saved for this very round is reused, a condition that does
not hold skips the step, and anything else executes the step's agent, telling
the observer how it goes (Observer). Review loops (``loops``) redo whole
stages: a node then runs again, in a later round, with the reviewer's feedback.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from langchain_core.runnables import Runnable, RunnableLambda

from api.exceptions import DomainError
from api.services.agent_types import AgentOutcome, AgentTask
from api.services.errors import as_domain_error
from api.services.multiagent.conditions import ConditionTexts, condition_holds
from api.services.multiagent.contracts import (
    RunControl,
    StepAgent,
    StepEvent,
    StepEventKind,
    StepResult,
    StepSpec,
)
from api.services.multiagent.loops import ReviewLoop
from api.services.multiagent.reviews import read_verdict
from api.services.multiagent.state import NO_PROGRESS, GraphState, GraphUpdate, LoopState
from api.services.prompts import Feedback, PromptFills, fill_prompt, merge_stage_outputs
from llm import exceptions as llm_exceptions

logger = logging.getLogger(__name__)


def agent_node_name(step: StepSpec) -> str:
    return f"agent_{step.stage}_{step.order}"


def join_node_name(position: int) -> str:
    return f"join_{position}"


@dataclass(frozen=True)
class RunNodes:
    """What every agent node of one run shares."""

    agent: StepAgent
    control: RunControl


@dataclass(frozen=True)
class _Attempt:
    """One execution of a step: what it was handed, the round it is in, and
    whether it already finished in an earlier round (a review loop redoes it)."""

    input_used: str
    round: int
    again: bool

    def event(
        self,
        kind: StepEventKind,
        step: StepSpec,
        result: StepResult | None = None,
        error: DomainError | None = None,
    ) -> StepEvent:
        return StepEvent(kind, step, self.input_used, result, error, self.round)


def _result(step: StepSpec, attempt: _Attempt, outcome: AgentOutcome) -> StepResult:
    """What a step produced. A reviewer's verdict line is read and taken out of
    its output; any other step's output is left exactly as it wrote it."""
    verdict, output = None, outcome.output
    if step.review is not None:
        reading = read_verdict(outcome.output)
        verdict, output = reading.verdict, reading.text
    return StepResult(
        step_order=step.order,
        stage=step.stage,
        title=step.title,
        model=step.model,
        input_used=attempt.input_used,
        output=output,
        tool_calls=outcome.tool_calls,
        usage=outcome.usage,
        rounds=attempt.round,
        verdict=verdict,
    )


async def _run_step(
    step: StepSpec, task: AgentTask, attempt: _Attempt, run: RunNodes
) -> StepResult:
    """Execute one step's agent, telling the observer how it goes."""
    notify = run.control.observer.on_step_event
    started = StepEventKind.RESTARTED if attempt.again else StepEventKind.STARTED
    await notify(attempt.event(started, step))
    try:
        outcome = await run.agent.execute(task)
    except asyncio.CancelledError:
        # The run was stopped, or a parallel step failed and LangGraph cancelled this one.
        await notify(attempt.event(StepEventKind.CANCELLED, step))
        raise
    except llm_exceptions.LLMError as cause:
        error = as_domain_error(cause)
        await notify(attempt.event(StepEventKind.FAILED, step, error=error))
        raise error from cause
    except DomainError as error:
        await notify(attempt.event(StepEventKind.FAILED, step, error=error))
        raise
    result = _result(step, attempt, outcome)
    await notify(attempt.event(StepEventKind.SUCCEEDED, step, result=result))
    return result


class StepNode:
    """The graph node of one step.

    ``position`` is its stage's place in the pipeline (from 0); ``loop`` is the
    review loop whose stages include it, if any: that is what makes its round
    a number above 1 once the work was sent back.
    """

    def __init__(
        self, step: StepSpec, position: int, run: RunNodes, loop: ReviewLoop | None
    ) -> None:
        self._step = step
        self._position = position
        self._run = run
        self._loop = loop

    async def run(self, state: GraphState) -> GraphUpdate:
        step = self._step
        loop_state = self._loop_state(state)
        round_ = loop_state.sent_back + 1
        saved = self._run.control.completed.get(step.order)
        if saved is not None and saved.rounds == round_:
            # An earlier attempt of this run already produced it, in this round.
            return {"results": {step.order: saved}}
        # A row that holds an earlier round's result is redone in place.
        again = saved is not None or step.order in state["results"]
        attempt = _Attempt(state["current_input"], round_, again)
        if self._holds(state):
            result = await self._execute(state, loop_state, attempt)
        else:
            result = await self._skip(attempt)
        return {"results": {step.order: result}}

    def _loop_state(self, state: GraphState) -> LoopState:
        if self._loop is None:
            return NO_PROGRESS
        return state["loops"].get(self._loop.reviewer, NO_PROGRESS)

    def _holds(self, state: GraphState) -> bool:
        condition = self._step.condition
        if condition is None:
            return True
        texts = ConditionTexts(
            previous_output=state["current_input"],
            inputs=state["values"],
            outputs={order: result.output for order, result in state["results"].items()},
        )
        return condition_holds(condition, texts)

    async def _skip(self, attempt: _Attempt) -> StepResult:
        step = self._step
        result = StepResult(
            step_order=step.order,
            stage=step.stage,
            title=step.title,
            model=step.model,
            input_used=attempt.input_used,
            output="",
            rounds=attempt.round,
            skipped=True,
        )
        await self._run.control.observer.on_step_event(
            attempt.event(StepEventKind.SKIPPED, step, result=result)
        )
        logger.info("pipeline.step_skipped step=%s round=%d", step.order, attempt.round)
        return result

    async def _execute(
        self, state: GraphState, loop_state: LoopState, attempt: _Attempt
    ) -> StepResult:
        step, control = self._step, self._run.control
        task = AgentTask(
            prompt=self._prompt(state, loop_state, attempt.round),
            model=step.model,
            role=step.role,
            allowed_tools=list(step.allowed_tools) if step.allowed_tools is not None else None,
            expected_output=step.expected_output,
            meter=control.meter(step.order),
            run_step=control.step_ref(step.order),
            reviewer=step.review is not None,
        )
        return await _run_step(step, task, attempt, self._run)

    def _prompt(self, state: GraphState, loop_state: LoopState, round_: int) -> str:
        loop, feedback = self._loop, None
        if loop is not None and loop_state.sent_back > 0:
            # Only the stage the work went back to is told to act on it unasked.
            feedback = Feedback(
                loop_state.feedback, round_, loop.rounds, block=self._position == loop.first
            )
        fills = PromptFills(
            state["current_input"],
            state["values"],
            first_stage=self._position == 0,
            feedback=feedback,
        )
        return fill_prompt(self._step.prompt, fills)


def agent_node(
    step: StepSpec, position: int, run: RunNodes, loop: ReviewLoop | None
) -> Runnable[GraphState, GraphUpdate]:
    return RunnableLambda(StepNode(step, position, run, loop).run)


def join_node(stage: list[StepSpec], position: int) -> Runnable[GraphState, GraphUpdate]:
    """Merge a stage's outputs into the next stage's input, in step order. A
    skipped step has none to give; a stage that skipped every step hands its own
    input on unchanged."""

    def join(state: GraphState) -> GraphUpdate:
        results = [state["results"][step.order] for step in stage]
        outputs = [(result.step_order, result.output) for result in results if not result.skipped]
        merged = merge_stage_outputs(outputs) if outputs else state["current_input"]
        return {"current_input": merged, "stage_inputs": {position + 1: merged}}

    return RunnableLambda(join)
