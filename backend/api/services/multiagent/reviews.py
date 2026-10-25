"""Review loops: a reviewer that can send the work back for fixes.

A step with a ``review`` is a normal agent step whose prompt judges the work. It
ends its answer with a line ``VERDICT: PASS`` or ``VERDICT: REVISE`` (the engine
adds that rule to the step's system prompt). When the reviewer's stage has
finished, the engine reads the last such line (``read_verdict``) and, on
``REVISE``, runs the stages from ``send_back_to_stage`` up to the reviewer's
again, at most ``max_rounds`` times.

Pure functions over plain values: the verdict rules, the stages a loop covers
and the save-time checks. The graph (``loops``), the save-time validation
(``pipeline_flow``) and the planner's sanitiser share them.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from api.models import STEP_REVIEW_MAX_ROUNDS


class Verdict(str, Enum):
    """What a reviewer decided about the work it was given."""

    PASS = "pass"
    REVISE = "revise"


@dataclass(frozen=True)
class _VerdictRule:
    #: How the reviewer writes it, after ``VERDICT:``.
    word: str
    #: Whether the work goes back to be fixed.
    sends_back: bool


#: Every verdict a reviewer can give (Strategy + Registry, AGENTS.md §5 O): a
#: new one is an entry here, not another branch in the graph.
VERDICTS: dict[Verdict, _VerdictRule] = {
    Verdict.PASS: _VerdictRule("PASS", sends_back=False),
    Verdict.REVISE: _VerdictRule("REVISE", sends_back=True),
}
_BY_WORD = {rule.word: verdict for verdict, rule in VERDICTS.items()}

#: A line holding only the verdict, which may be dressed in Markdown (``**VERDICT: PASS**``,
#: ``> VERDICT: REVISE``) or end in a full stop; a line with anything else on it is not one.
_VERDICT_LINE = re.compile(
    r"^[ \t>*_`#-]*VERDICT[ \t]*:[ \t*_`]*("
    + "|".join(re.escape(word) for word in _BY_WORD)
    + r")[ \t\r*_`.!]*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class VerdictReading:
    """A reviewer's answer: the verdict its last verdict line gave (None when it
    has none) and the answer without that line."""

    verdict: Verdict | None
    text: str


def read_verdict(output: str) -> VerdictReading:
    """Find the last verdict line of ``output`` and take it out of the text."""
    lines = list(_VERDICT_LINE.finditer(output))
    if not lines:
        return VerdictReading(None, output)
    last = lines[-1]
    end = last.end() + 1 if output[last.end() : last.end() + 1] == "\n" else last.end()
    text = (output[: last.start()] + output[end:]).strip()
    return VerdictReading(_BY_WORD[last.group(1).upper()], text)


def sends_work_back(verdict: Verdict | None) -> bool:
    """Whether this verdict (None: none given) sends the work back."""
    return verdict is not None and VERDICTS[verdict].sends_back


@dataclass(frozen=True)
class StepReview:
    """Makes a step a reviewer (§7 Value Object).

    ``send_back_to_stage`` is a stage number before the step's own. ``max_rounds``
    is how many times the work may be sent back, so the stages run at most
    ``1 + max_rounds`` times.
    """

    send_back_to_stage: int
    max_rounds: int


class ReviewStep(Protocol):
    """What the loop rules read of a step."""

    @property
    def order(self) -> int: ...

    @property
    def stage(self) -> int: ...

    @property
    def review(self) -> StepReview | None: ...


@dataclass(frozen=True)
class ReviewSpan:
    """The stages one review loop covers, by stage number."""

    #: The review step's order.
    reviewer: int
    #: The stage the work goes back to, and the reviewer's own stage.
    first: int
    last: int
    max_rounds: int

    def overlaps(self, other: ReviewSpan) -> bool:
        return self.first <= other.last and other.first <= self.last


def review_spans(steps: Iterable[ReviewStep]) -> list[ReviewSpan]:
    """The loop of every reviewer, from the one that starts first."""
    spans = [
        ReviewSpan(step.order, step.review.send_back_to_stage, step.stage, step.review.max_rounds)
        for step in steps
        if step.review is not None
    ]
    return sorted(spans, key=lambda span: (span.first, span.last, span.reviewer))


def overlapping(spans: list[ReviewSpan]) -> list[tuple[ReviewSpan, ReviewSpan]]:
    """Each loop that shares a stage with one before it, with the first such loop.
    Dropping the first of every pair leaves loops that cannot overlap."""
    clashes: list[tuple[ReviewSpan, ReviewSpan]] = []
    kept: list[ReviewSpan] = []
    for span in spans:
        clash = next((other for other in kept if span.overlaps(other)), None)
        if clash is None:
            kept.append(span)
        else:
            clashes.append((span, clash))
    return clashes


def rounds_problem(max_rounds: int) -> str | None:
    """Why a review cannot send the work back this many times, or None. A plain
    phrase that continues "its review loop ..."."""
    if 1 <= max_rounds <= STEP_REVIEW_MAX_ROUNDS:
        return None
    return f"can send the work back from 1 to {STEP_REVIEW_MAX_ROUNDS} times"


def review_problem(review: StepReview, stage: int, stages: Collection[int]) -> str | None:
    """Why a review on a step in ``stage`` cannot work in a pipeline whose steps
    sit in ``stages``, or None. A plain phrase that continues "its review loop ..."."""
    if (problem := rounds_problem(review.max_rounds)) is not None:
        return problem
    if review.send_back_to_stage >= stage:
        return "can only send the work back to an earlier stage"
    if review.send_back_to_stage not in stages:
        return f"sends the work back to stage {review.send_back_to_stage}, which has no steps"
    return None


def review_from_data(raw: object) -> StepReview | None:
    """A review read from stored or planner JSON; None when it is absent or
    malformed (that data is never trusted to be well formed)."""
    if not isinstance(raw, Mapping):
        return None
    data: Mapping[str, Any] = raw
    stage, rounds = _whole(data.get("send_back_to_stage")), _whole(data.get("max_rounds"))
    return None if stage is None or rounds is None else StepReview(stage, rounds)


def _whole(value: object) -> int | None:
    """A whole number as an int; numbers a planner wrote as text too, anything else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = value.strip() if isinstance(value, str) else ""
    return int(text) if text.isascii() and text.isdecimal() else None
