"""Conditional steps: "run this step only if ...".

A step's condition compares one piece of text with the text the person typed.
It is read when the step is about to start; when it does not hold the step is
skipped. Pure functions over plain values, so the rules are tested on their own
and shared by the engine (``graph``), the save-time checks (``pipeline_flow``)
and the planner's sanitiser (``pipelines.sanitise_step``).

What a condition may look at (``CONDITION_SOURCES``, one entry per kind):

- ``previous_output``: what the previous stage handed on, the step's ``{input}``
  (in the first stage, the run's own text);
- ``input:<name>``: a named input of the pipeline;
- ``step:<order>``: the output of a step in an earlier stage.

How the text is compared (``CONDITION_OPERATORS``): both sides trimmed and
case-insensitive.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from api.models import STEP_CONDITION_VALUE_MAX_LENGTH

#: The separator in a source with a key: ``input:topic``, ``step:2``.
SOURCE_KEY_SEPARATOR = ":"
_STEP_KEY = re.compile(r"[0-9]+")


@dataclass(frozen=True)
class StepCondition:
    """A step runs only while this holds (§7 Value Object).

    ``value`` is what the operator compares the source with; it is ignored by
    the operators that take none (``is_empty``, ``not_empty``).
    """

    source: str
    operator: str
    value: str = ""


@dataclass(frozen=True)
class ConditionTexts:
    """What a condition can look at once its step is about to start."""

    previous_output: str
    #: The run's named inputs, by name.
    inputs: Mapping[str, str]
    #: The outputs of the steps that finished, by step order (a skipped one is "").
    outputs: Mapping[int, str]


@dataclass(frozen=True)
class ConditionScope:
    """What a condition may refer to when it is saved."""

    #: The names of the pipeline's declared inputs.
    inputs: frozenset[str]
    #: The orders of the steps in stages before the condition's own step.
    earlier_steps: frozenset[int]


@dataclass(frozen=True)
class _Operator:
    """How one kind of comparison reads its two (already normalised) texts."""

    holds: Callable[[str, str], bool]
    takes_value: bool = True


#: Every comparison a condition can make (Strategy + Registry, AGENTS.md §5 O).
CONDITION_OPERATORS: dict[str, _Operator] = {
    "contains": _Operator(lambda text, value: value in text),
    "not_contains": _Operator(lambda text, value: value not in text),
    "equals": _Operator(lambda text, value: text == value),
    "not_equals": _Operator(lambda text, value: text != value),
    "is_empty": _Operator(lambda text, value: text == "", takes_value=False),
    "not_empty": _Operator(lambda text, value: text != "", takes_value=False),
}


def _no_key(key: str, scope: ConditionScope) -> str | None:
    return None if key == "" else "looks at the previous result, which has nothing after its name"


def _input_problem(key: str, scope: ConditionScope) -> str | None:
    if key in scope.inputs:
        return None
    return f"looks at the input “{key}”, which this pipeline does not have"


def _step_number(key: str) -> int | None:
    return int(key) if _STEP_KEY.fullmatch(key) else None


def _step_problem(key: str, scope: ConditionScope) -> str | None:
    number = _step_number(key)
    if number is None:
        return "looks at a step by its number, like step:2"
    if number in scope.earlier_steps:
        return None
    return f"looks at step {number}, which does not run before it (pick a step in an earlier stage)"


def _read_step(key: str, texts: ConditionTexts) -> str:
    number = _step_number(key)
    return "" if number is None else texts.outputs.get(number, "")


@dataclass(frozen=True)
class _Source:
    """One kind of source: why a key is not usable in a saved pipeline, and how
    the text is read while a run executes."""

    problem: Callable[[str, ConditionScope], str | None]
    read: Callable[[str, ConditionTexts], str]


#: Every kind of source a condition can look at (Strategy + Registry, §5 O).
CONDITION_SOURCES: dict[str, _Source] = {
    "previous_output": _Source(_no_key, lambda key, texts: texts.previous_output),
    "input": _Source(_input_problem, lambda key, texts: texts.inputs.get(key, "")),
    "step": _Source(_step_problem, _read_step),
}


def split_source(source: str) -> tuple[str, str]:
    """``input:topic`` as ``("input", "topic")``; a source without a key as ``(kind, "")``."""
    kind, _, key = source.strip().partition(SOURCE_KEY_SEPARATOR)
    return kind.strip(), key.strip()


def _normal(text: str) -> str:
    return text.strip().casefold()


def condition_holds(condition: StepCondition, texts: ConditionTexts) -> bool:
    """Whether the step may run. A condition that cannot be read (an operator or
    a source this build does not know) never holds: the step is skipped."""
    operator = CONDITION_OPERATORS.get(condition.operator)
    kind, key = split_source(condition.source)
    source = CONDITION_SOURCES.get(kind)
    if operator is None or source is None:
        return False
    return operator.holds(_normal(source.read(key, texts)), _normal(condition.value))


def shape_problem(condition: StepCondition) -> str | None:
    """Why the condition cannot be saved whatever the pipeline holds (the
    operator, the value and the kind of source), or None. A plain phrase that
    continues "its condition ..."."""
    operator = CONDITION_OPERATORS.get(condition.operator)
    if operator is None:
        return f"compares in a way AIMIx does not know (“{condition.operator}”)"
    if split_source(condition.source)[0] not in CONDITION_SOURCES:
        return "needs something to look at: the previous result, an input or an earlier step"
    value = condition.value.strip()
    if len(value) > STEP_CONDITION_VALUE_MAX_LENGTH:
        return f"has text over {STEP_CONDITION_VALUE_MAX_LENGTH} characters long"
    if operator.takes_value and not value:
        return "needs the text to compare with"
    return None


def condition_problem(condition: StepCondition, scope: ConditionScope) -> str | None:
    """Why the condition cannot work in a pipeline with this ``scope``, or None."""
    if (problem := shape_problem(condition)) is not None:
        return problem
    kind, key = split_source(condition.source)
    return CONDITION_SOURCES[kind].problem(key, scope)


def tidy(condition: StepCondition) -> StepCondition:
    """The condition as it is stored: trimmed, and without a value the operator ignores."""
    operator = CONDITION_OPERATORS.get(condition.operator)
    value = condition.value.strip() if operator is None or operator.takes_value else ""
    return StepCondition(condition.source.strip(), condition.operator.strip(), value)


def condition_from_data(raw: object) -> StepCondition | None:
    """A condition read from stored or planner JSON, tidied; None when it is
    absent or malformed (that data is never trusted to be well formed)."""
    if not isinstance(raw, Mapping):
        return None
    data: Mapping[str, Any] = raw
    source, operator, value = data.get("source"), data.get("operator"), data.get("value")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(value)  # a planner may write a number where text is meant
    if value is None:
        value = ""
    if not (isinstance(source, str) and isinstance(operator, str) and isinstance(value, str)):
        return None
    return tidy(StepCondition(source, operator, value))
