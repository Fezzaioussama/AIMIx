"""Checks that a pipeline's conditions and review loops can work (AGENTS.md §6,
fail fast): when it is saved, when a run starts, and when a planner proposes one.

A step's condition may look at the previous result, at one of the pipeline's
named inputs and at steps in earlier stages; a step's review sends the work back
to an earlier stage that exists, and two review loops never share a stage (the
simpler of the two ways to keep every loop bounded: a stage is in at most one
loop, so every step has one round counter and ``1 + max_rounds`` is the most
times it runs). One pure function finds the problems; callers decide what to do
with them: refuse (``ensure_valid``) or drop what cannot work (the planner).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from api.exceptions import ValidationFailed
from api.models import Pipeline, PipelineStep
from api.repositories.pipelines import PipelineChanges
from api.services.multiagent.conditions import (
    ConditionScope,
    StepCondition,
    condition_from_data,
    condition_problem,
)
from api.services.multiagent.contracts import PipelineSpec
from api.services.multiagent.reviews import (
    StepReview,
    overlapping,
    review_from_data,
    review_problem,
    review_spans,
)

FlowField = Literal["condition", "review"]


@dataclass(frozen=True)
class FlowStep:
    """What the flow rules read of a step (§7 Value Object)."""

    order: int
    stage: int
    title: str
    condition: StepCondition | None = None
    review: StepReview | None = None

    @property
    def label(self) -> str:
        """The step as a person names it: "Step 3 (Publish)", or "Step 3"."""
        title = self.title.strip()
        return f"Step {self.order} ({title})" if title else f"Step {self.order}"


@dataclass(frozen=True)
class FlowProblem:
    """One thing that cannot work, on one field of one step."""

    order: int
    field: FlowField
    #: A whole sentence for a person: "Step 3 (Publish): its condition ...".
    message: str


def flow_step(data: Mapping[str, Any]) -> FlowStep:
    """A step's flow fields read from JSON (a request, a planner's plan, a row)."""
    return FlowStep(
        order=int(data.get("order") or 0),
        stage=int(data.get("stage") or 0),
        title=str(data.get("title") or ""),
        condition=condition_from_data(data.get("condition")),
        review=review_from_data(data.get("review")),
    )


def flow_problems(inputs: Collection[str], steps: Sequence[FlowStep]) -> list[FlowProblem]:
    """Everything that stops these steps' conditions and review loops from working.
    ``inputs`` are the names the pipeline declares."""
    stages = {step.stage for step in steps}
    problems = [problem for step in steps for problem in _condition_problems(step, inputs, steps)]
    problems += [problem for step in steps for problem in _review_problems(step, stages)]
    return problems + _overlap_problems(steps, stages)


def _condition_problems(
    step: FlowStep, inputs: Collection[str], steps: Sequence[FlowStep]
) -> list[FlowProblem]:
    if step.condition is None:
        return []
    earlier = frozenset(other.order for other in steps if other.stage < step.stage)
    problem = condition_problem(step.condition, ConditionScope(frozenset(inputs), earlier))
    if problem is None:
        return []
    return [FlowProblem(step.order, "condition", f"{step.label}: its condition {problem}.")]


def _review_problems(step: FlowStep, stages: Collection[int]) -> list[FlowProblem]:
    if step.review is None:
        return []
    problem = review_problem(step.review, step.stage, stages)
    if problem is None:
        return []
    return [FlowProblem(step.order, "review", f"{step.label}: its review loop {problem}.")]


def _overlap_problems(steps: Sequence[FlowStep], stages: Collection[int]) -> list[FlowProblem]:
    """A loop that shares a stage with an earlier one is the one at fault (the
    loops that already have another problem are left to report it)."""
    by_order = {step.order: step for step in steps}
    sound = [
        span
        for span in review_spans(steps)
        if review_problem(StepReview(span.first, span.max_rounds), span.last, stages) is None
    ]
    return [
        FlowProblem(
            span.reviewer,
            "review",
            f"{by_order[span.reviewer].label}: its review loop shares stages with the one of "
            f"{by_order[other.reviewer].label}. Review loops cannot overlap.",
        )
        for span, other in overlapping(sound)
    ]


def ensure_valid(inputs: Collection[str], steps: Sequence[FlowStep]) -> None:
    """Raise ``ValidationFailed`` (400) saying every problem, in plain words."""
    problems = flow_problems(inputs, steps)
    if problems:
        raise ValidationFailed(" ".join(problem.message for problem in problems))


def ensure_valid_flow(changes: PipelineChanges, current: Pipeline | None = None) -> None:
    """Refuse a save that would leave the pipeline with a condition or a review
    loop that cannot work. A change that leaves out the steps (or the inputs)
    keeps ``current``'s, which are then checked against the new inputs (or steps)."""
    names = _input_names(changes.inputs if changes.inputs is not None else _stored_inputs(current))
    if changes.steps is not None:
        steps = [flow_step(step) for step in changes.steps]
    else:
        steps = [] if current is None else [_stored_step(step) for step in current.steps]
    ensure_valid(names, steps)


def ensure_valid_spec(spec: PipelineSpec) -> None:
    """The same check on the snapshot a run is about to execute."""
    steps = [FlowStep(s.order, s.stage, s.title, s.condition, s.review) for s in spec.steps]
    ensure_valid([field.name for field in spec.inputs], steps)


def _stored_inputs(current: Pipeline | None) -> list[dict[str, str]]:
    return [] if current is None else list(current.inputs or [])


def _input_names(inputs: Sequence[Mapping[str, str]]) -> list[str]:
    return [item["name"] for item in inputs]


def _stored_step(step: PipelineStep) -> FlowStep:
    return FlowStep(
        step.order,
        step.stage,
        step.title or "",
        condition_from_data(step.condition),
        review_from_data(step.review),
    )
