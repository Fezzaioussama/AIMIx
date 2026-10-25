"""Conditional steps' rules, on their own: how text is compared, what a condition
can look at, and what makes one unusable when a pipeline is saved."""

from __future__ import annotations

import pytest

from api.models import STEP_CONDITION_VALUE_MAX_LENGTH
from api.services.multiagent.conditions import (
    CONDITION_OPERATORS,
    CONDITION_SOURCES,
    ConditionScope,
    ConditionTexts,
    StepCondition,
    condition_from_data,
    condition_holds,
    condition_problem,
    shape_problem,
    split_source,
    tidy,
)

TEXTS = ConditionTexts(
    previous_output="  Hello Blog World \n",
    inputs={"topic": "Bees and Honey", "blank": "   "},
    outputs={1: "First DRAFT", 2: ""},
)
SCOPE = ConditionScope(inputs=frozenset({"topic"}), earlier_steps=frozenset({1, 2}))


def holds(operator: str, value: str = "", source: str = "previous_output") -> bool:
    return condition_holds(StepCondition(source, operator, value), TEXTS)


@pytest.mark.parametrize(
    ("operator", "value", "expected"),
    [
        ("contains", "blog", True),
        ("contains", "  BLOG  ", True),
        ("contains", "hello blog world", True),
        ("contains", "news", False),
        ("not_contains", "news", True),
        ("not_contains", "Blog", False),
        ("equals", "hello blog world", True),
        ("equals", "HELLO BLOG WORLD  ", True),
        ("equals", "hello blog", False),
        ("not_equals", "hello blog", True),
        ("not_equals", "Hello Blog World", False),
        ("is_empty", "", False),
        ("not_empty", "", True),
        # The value of is_empty and not_empty is ignored.
        ("is_empty", "anything", False),
        ("not_empty", "anything", True),
    ],
)
def test_the_operators_compare_trimmed_text_ignoring_case(
    operator: str, value: str, expected: bool
) -> None:
    assert holds(operator, value) is expected


@pytest.mark.parametrize(
    ("operator", "value", "expected"),
    [
        ("is_empty", "", True),
        ("not_empty", "", False),
        ("equals", "", True),
        ("contains", "x", False),
        ("not_contains", "x", True),
    ],
)
def test_blank_text_counts_as_empty(operator: str, value: str, expected: bool) -> None:
    assert holds(operator, value, source="input:blank") is expected


def test_every_operator_is_in_the_registry_and_only_two_ignore_their_value() -> None:
    assert set(CONDITION_OPERATORS) == {
        "contains",
        "not_contains",
        "equals",
        "not_equals",
        "is_empty",
        "not_empty",
    }
    assert {name for name, op in CONDITION_OPERATORS.items() if not op.takes_value} == {
        "is_empty",
        "not_empty",
    }


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("previous_output", "hello blog world"),
        ("input:topic", "bees and honey"),
        ("step:1", "first draft"),
        ("step:2", ""),
        # A source that reads nothing reads empty text; it is never an error mid-run.
        ("input:missing", ""),
        ("step:9", ""),
        ("step:x", ""),
    ],
)
def test_each_source_reads_its_text(source: str, expected: str) -> None:
    assert holds("equals", expected, source=source)


def test_a_source_or_operator_this_build_does_not_know_never_holds() -> None:
    assert not holds("sounds_like", "x")
    assert not holds("is_empty", "", source="weather:today")
    # ... not even a negative comparison: the step is skipped, not run by accident.
    assert not holds("not_contains", "x", source="weather:today")


def test_the_registry_names_every_kind_of_source() -> None:
    assert set(CONDITION_SOURCES) == {"previous_output", "input", "step"}


@pytest.mark.parametrize(
    ("source", "parts"),
    [
        ("previous_output", ("previous_output", "")),
        ("input:topic", ("input", "topic")),
        (" step : 2 ", ("step", "2")),
        ("input:a:b", ("input", "a:b")),
        ("", ("", "")),
    ],
)
def test_a_source_splits_into_its_kind_and_key(source: str, parts: tuple[str, str]) -> None:
    assert split_source(source) == parts


def problem(operator: str, value: str = "", source: str = "previous_output") -> str | None:
    return condition_problem(StepCondition(source, operator, value), SCOPE)


def test_a_usable_condition_has_no_problem() -> None:
    assert problem("contains", "blog") is None
    assert problem("is_empty") is None
    assert problem("equals", "x", source="input:topic") is None
    assert problem("not_empty", source="step:2") is None


def test_an_unknown_operator_is_a_problem_that_names_it() -> None:
    assert problem("sounds_like", "x") == ("compares in a way AIMIx does not know (“sounds_like”)")


def test_an_unknown_kind_of_source_is_a_problem() -> None:
    assert problem("contains", "x", source="weather:today") == (
        "needs something to look at: the previous result, an input or an earlier step"
    )
    assert problem("contains", "x", source="") is not None


def test_a_value_may_have_up_to_the_limit_and_not_one_more() -> None:
    assert problem("contains", "x" * STEP_CONDITION_VALUE_MAX_LENGTH) is None
    too_long = problem("contains", "x" * (STEP_CONDITION_VALUE_MAX_LENGTH + 1))
    assert too_long == f"has text over {STEP_CONDITION_VALUE_MAX_LENGTH} characters long"


def test_the_length_of_the_value_is_measured_without_surrounding_spaces() -> None:
    padded = "  " + "x" * STEP_CONDITION_VALUE_MAX_LENGTH + "  "
    assert problem("contains", padded) is None


def test_an_operator_that_compares_needs_text_to_compare_with() -> None:
    assert problem("contains", "   ") == "needs the text to compare with"
    assert problem("equals", "") == "needs the text to compare with"
    assert problem("is_empty", "") is None


def test_an_input_must_be_declared() -> None:
    assert problem("contains", "x", source="input:audience") == (
        "looks at the input “audience”, which this pipeline does not have"
    )


def test_a_step_must_run_in_an_earlier_stage() -> None:
    reason = problem("contains", "x", source="step:5")
    assert reason is not None and "step 5, which does not run before it" in reason
    assert problem("contains", "x", source="step:two") == (
        "looks at a step by its number, like step:2"
    )
    assert problem("contains", "x", source="step:") is not None


def test_the_previous_result_takes_nothing_after_its_name() -> None:
    assert problem("contains", "x", source="previous_output:1") is not None


def test_shape_problems_do_not_depend_on_the_pipeline() -> None:
    assert shape_problem(StepCondition("input:anything", "contains", "x")) is None
    assert shape_problem(StepCondition("step:99", "contains", "x")) is None
    assert shape_problem(StepCondition("input:a", "nope", "x")) is not None


def test_tidy_trims_and_drops_a_value_the_operator_ignores() -> None:
    assert tidy(StepCondition(" input:topic ", " contains ", "  bees ")) == StepCondition(
        "input:topic", "contains", "bees"
    )
    assert tidy(StepCondition("previous_output", "is_empty", "leftover")) == StepCondition(
        "previous_output", "is_empty", ""
    )
    # An operator nobody knows keeps what it was given, for the problem to report.
    assert tidy(StepCondition("previous_output", "nope", " x ")).value == "x"


@pytest.mark.parametrize(
    "raw",
    [None, "contains", ["a"], 3, {}, {"source": "previous_output"}, {"operator": "contains"}],
)
def test_malformed_condition_data_reads_as_no_condition(raw: object) -> None:
    assert condition_from_data(raw) is None


def test_condition_data_is_read_tidied_and_forgiving_about_the_value() -> None:
    assert condition_from_data(
        {"source": " step:1 ", "operator": "contains", "value": " blog "}
    ) == StepCondition("step:1", "contains", "blog")
    assert condition_from_data(
        {"source": "previous_output", "operator": "is_empty", "value": None}
    ) == StepCondition("previous_output", "is_empty", "")
    assert condition_from_data(
        {"source": "previous_output", "operator": "contains", "value": 2024}
    ) == StepCondition("previous_output", "contains", "2024")
    # A flag is not a number.
    assert (
        condition_from_data({"source": "previous_output", "operator": "contains", "value": True})
        is None
    )
