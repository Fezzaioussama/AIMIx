"""Review loops in the pipeline graph (AGENTS.md §7 Strategy: one loop per reviewer).

A loop covers the stages from the one its reviewer sends the work back to, up to
the reviewer's own. When that stage's join has merged its outputs, a conditional
edge reads the reviewer's verdict: ``REVISE`` with rounds left goes to a "back"
node that starts the target stage over (with its original input and the
reviewer's feedback); anything else carries on to the next stage.

The loop's state lives in the graph state (``GraphState.loops``): how many times
the work was sent back, and the feedback of the last time. A resumed run builds
it again from the rows its earlier attempt saved (``initial_loops``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from langchain_core.runnables import Runnable, RunnableLambda
from langgraph.graph import StateGraph

from api.services.multiagent.contracts import RunControl, StepSpec
from api.services.multiagent.reviews import (
    ReviewSpan,
    StepReview,
    overlapping,
    review_problem,
    review_spans,
    sends_work_back,
)
from api.services.multiagent.state import NO_PROGRESS, GraphState, GraphUpdate, LoopState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReviewLoop:
    """One reviewer's loop, by stage position (the stage list's index, from 0)."""

    #: The reviewer's step order.
    reviewer: int
    #: The stage the work goes back to, and the reviewer's own.
    first: int
    last: int
    max_rounds: int
    #: The orders of every step in the loop's stages.
    members: frozenset[int]

    @property
    def rounds(self) -> int:
        """How many times its stages run, at most."""
        return 1 + self.max_rounds

    def covers(self, position: int) -> bool:
        return self.first <= position <= self.last


def find_loops(stages: list[list[StepSpec]]) -> list[ReviewLoop]:
    """The loops a run follows. A review that cannot work (it points at a stage
    that is not earlier, or its stages are shared with another loop) is ignored
    and logged: saving refuses those, so only unvalidated data gets here, and
    the run must stay bounded whatever it holds."""
    positions = {stage[0].stage: position for position, stage in enumerate(stages)}
    steps = [step for stage in stages for step in stage]
    usable = [span for span in review_spans(steps) if _works(span, positions)]
    clashing = {span for span, _ in overlapping(usable)}
    for span in {span for span in review_spans(steps) if span not in usable} | clashing:
        logger.warning("pipeline.review_ignored reviewer=%s", span.reviewer)
    return [_loop(span, stages, positions) for span in usable if span not in clashing]


def _works(span: ReviewSpan, positions: dict[int, int]) -> bool:
    review = StepReview(span.first, span.max_rounds)
    return review_problem(review, span.last, positions) is None


def _loop(span: ReviewSpan, stages: list[list[StepSpec]], positions: dict[int, int]) -> ReviewLoop:
    first, last = positions[span.first], positions[span.last]
    members = frozenset(step.order for stage in stages[first : last + 1] for step in stage)
    return ReviewLoop(span.reviewer, first, last, span.max_rounds, members)


def loop_covering(loops: list[ReviewLoop], position: int) -> ReviewLoop | None:
    """The loop whose stages include ``position``; loops never share a stage."""
    return next((loop for loop in loops if loop.covers(position)), None)


def initial_loops(loops: list[ReviewLoop], control: RunControl) -> dict[int, LoopState]:
    """Where a resumed run's loops stand, read from the rows it saved.

    A step's row keeps the round it was last in, so the newest round any step of
    a loop reached is the round the loop was in: the work had been sent back
    one time fewer. The reviewer's saved answer is the feedback of that last
    time, while it still holds it (it has not run again in that round).
    """
    states: dict[int, LoopState] = {}
    for loop in loops:
        latest = max((control.rounds.get(order, 1) for order in loop.members), default=1)
        if latest > 1:
            states[loop.reviewer] = LoopState(latest - 1, _carried_feedback(loop, control, latest))
    return states


def _carried_feedback(loop: ReviewLoop, control: RunControl, latest: int) -> str:
    saved = control.completed.get(loop.reviewer)
    if saved is not None and saved.rounds == latest - 1 and sends_work_back(saved.verdict):
        return saved.output
    return ""


def recursion_limit(stage_count: int, loops: list[ReviewLoop]) -> int:
    """How many supersteps a run may take: a node and a join per stage (plus
    slack, as before), and for each loop, every time the work may be sent back,
    the stages it covers again and the way back."""
    again = sum(loop.max_rounds * (2 * (loop.last - loop.first + 1) + 1) for loop in loops)
    return 2 * stage_count + 2 + again


def back_node_name(loop: ReviewLoop) -> str:
    return f"back_{loop.reviewer}"


@dataclass(frozen=True)
class LoopWays:
    """Where a reviewer's stage can lead: its join, the nodes it goes back to
    and the nodes it carries on to (the next stage's, or the end)."""

    join: str
    back_to: list[str]
    forward: list[str]


def add_loop(builder: StateGraph, loop: ReviewLoop, ways: LoopWays) -> None:
    """Wire the loop's join to either way (the conditional edge) and give the
    "back" node its edges into the stage it restarts."""
    back = back_node_name(loop)
    builder.add_node(back, _back_node(loop))
    for name in ways.back_to:
        builder.add_edge(back, name)
    builder.add_conditional_edges(
        ways.join, _router(loop, back, ways.forward), [back, *ways.forward]
    )


def _router(loop: ReviewLoop, back: str, forward: list[str]) -> Callable[[GraphState], list[str]]:
    def route(state: GraphState) -> list[str]:
        reviewer = state["results"].get(loop.reviewer)
        sent_back = state["loops"].get(loop.reviewer, NO_PROGRESS).sent_back
        wants = reviewer is not None and sends_work_back(reviewer.verdict)
        if wants and sent_back < loop.max_rounds:
            return [back]
        if wants:
            logger.info("pipeline.review_accepted reviewer=%s rounds=%d", loop.reviewer, sent_back)
        return forward

    return route


def _back_node(loop: ReviewLoop) -> Runnable[GraphState, GraphUpdate]:
    def go_back(state: GraphState) -> GraphUpdate:
        reviewer = state["results"][loop.reviewer]
        sent_back = state["loops"].get(loop.reviewer, NO_PROGRESS).sent_back + 1
        logger.info(
            "pipeline.review_sent_back reviewer=%s round=%d of=%d",
            loop.reviewer,
            sent_back + 1,
            loop.rounds,
        )
        return {
            "current_input": state["stage_inputs"][loop.first],
            "loops": {loop.reviewer: LoopState(sent_back, reviewer.output)},
        }

    return RunnableLambda(go_back)
