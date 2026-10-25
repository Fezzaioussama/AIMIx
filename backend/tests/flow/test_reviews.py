"""Review loops' rules, on their own: reading a reviewer's verdict, the stages a
loop covers, and what makes a review unusable when a pipeline is saved."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from api.models import STEP_REVIEW_MAX_ROUNDS
from api.services.multiagent.reviews import (
    VERDICTS,
    ReviewSpan,
    StepReview,
    Verdict,
    VerdictReading,
    overlapping,
    read_verdict,
    review_from_data,
    review_problem,
    review_spans,
    rounds_problem,
    sends_work_back,
)

PASS, REVISE = Verdict.PASS, Verdict.REVISE


@pytest.mark.parametrize(
    ("output", "verdict", "text"),
    [
        # The usual way: the last line.
        ("Looks good.\nVERDICT: PASS", PASS, "Looks good."),
        ("Shorten the intro.\n\nVERDICT: REVISE\n", REVISE, "Shorten the intro."),
        ("VERDICT: PASS", PASS, ""),
        # Case and spacing.
        ("verdict: pass", PASS, ""),
        ("Verdict: Revise", REVISE, ""),
        ("  VERDICT :   Revise  ", REVISE, ""),
        ("VERDICT:PASS", PASS, ""),
        ("\tVERDICT:\tPASS\t", PASS, ""),
        # Markdown around the line, and a full stop after it.
        ("**VERDICT: PASS**", PASS, ""),
        ("**VERDICT:** PASS", PASS, ""),
        ("> VERDICT: REVISE", REVISE, ""),
        ("- VERDICT: REVISE", REVISE, ""),
        ("## Verdict: PASS", PASS, ""),
        ("`VERDICT: PASS`", PASS, ""),
        ("VERDICT: PASS.", PASS, ""),
        ("VERDICT: REVISE!", REVISE, ""),
        # Windows line ends.
        ("Notes\r\nVERDICT: PASS\r\n", PASS, "Notes"),
        # Not the last line: the verdict still counts, and only its line goes.
        ("A\nVERDICT: REVISE\nB", REVISE, "A\nB"),
        ("VERDICT: PASS\nthe rest of it", PASS, "the rest of it"),
        # Two verdicts: the last one counts and only it is removed.
        ("VERDICT: REVISE\nFixed it.\nVERDICT: PASS", PASS, "VERDICT: REVISE\nFixed it."),
        (
            "VERDICT: PASS\nOn second thought...\nVERDICT: REVISE",
            REVISE,
            "VERDICT: PASS\nOn second thought...",
        ),
        # No verdict.
        ("Good work.", None, "Good work."),
        ("", None, ""),
        ("VERDICT PASS", None, "VERDICT PASS"),
        ("VERDICT: PASSED", None, "VERDICT: PASSED"),
        ("VERDICT: MAYBE", None, "VERDICT: MAYBE"),
        ("VERDICT: PASS because it is good", None, "VERDICT: PASS because it is good"),
        ("My verdict: pass the salt", None, "My verdict: pass the salt"),
        ("The verdict is PASS", None, "The verdict is PASS"),
    ],
)
def test_the_last_verdict_line_is_read_and_taken_out(
    output: str, verdict: Verdict | None, text: str
) -> None:
    assert read_verdict(output) == VerdictReading(verdict, text)


def test_text_around_a_verdict_in_the_middle_keeps_its_own_lines() -> None:
    reading = read_verdict("First\n\nVERDICT: REVISE\n\nLast")
    assert reading.text == "First\n\n\nLast"


def test_a_missing_verdict_leaves_the_text_exactly_as_it_was() -> None:
    text = "  Indented answer\n\nwith blank lines  \n"
    assert read_verdict(text) == VerdictReading(None, text)


def test_only_the_revise_verdict_sends_the_work_back() -> None:
    assert sends_work_back(REVISE) is True
    assert sends_work_back(PASS) is False
    assert sends_work_back(None) is False


def test_every_verdict_is_in_the_registry_with_the_word_a_reviewer_writes() -> None:
    assert {verdict: rule.word for verdict, rule in VERDICTS.items()} == {
        PASS: "PASS",
        REVISE: "REVISE",
    }


@dataclass(frozen=True)
class Reviewer:
    order: int
    stage: int
    review: StepReview | None


def spans(*reviewers: tuple[int, int, int, int]) -> list[ReviewSpan]:
    """Loops given as (reviewer order, reviewer stage, send back to, max rounds)."""
    return review_spans(
        Reviewer(order, stage, StepReview(target, rounds))
        for order, stage, target, rounds in reviewers
    )


def test_a_loop_covers_the_stages_from_its_target_to_its_reviewer() -> None:
    [span] = spans((5, 4, 2, 3))
    assert span == ReviewSpan(reviewer=5, first=2, last=4, max_rounds=3)


def test_steps_without_a_review_have_no_loop() -> None:
    assert review_spans([Reviewer(1, 1, None), Reviewer(2, 2, StepReview(1, 1))]) == [
        ReviewSpan(2, 1, 2, 1)
    ]


def test_loops_are_listed_from_the_one_that_starts_first() -> None:
    first, second = spans((9, 6, 5, 1), (4, 3, 1, 1))
    assert (first.first, second.first) == (1, 5)


def test_loops_in_separate_stages_do_not_overlap() -> None:
    assert overlapping(spans((3, 3, 2, 1), (6, 6, 5, 2), (8, 8, 7, 1))) == []


def test_loops_that_touch_at_one_stage_overlap() -> None:
    [(late, early)] = overlapping(spans((3, 3, 1, 1), (5, 5, 3, 1)))
    assert (early.reviewer, late.reviewer) == (3, 5)


def test_a_loop_inside_another_overlaps_it() -> None:
    [(inner, outer)] = overlapping(spans((6, 6, 2, 1), (4, 4, 3, 1)))
    assert (outer.reviewer, inner.reviewer) == (6, 4)


def test_two_reviewers_in_one_stage_overlap() -> None:
    [(second, first)] = overlapping(spans((3, 3, 2, 1), (4, 3, 2, 1)))
    assert (first.reviewer, second.reviewer) == (3, 4)


def test_each_late_loop_is_reported_once_against_the_first_it_clashes_with() -> None:
    pairs = overlapping(spans((3, 3, 1, 1), (4, 4, 2, 1), (5, 5, 3, 1)))
    assert [(late.reviewer, early.reviewer) for late, early in pairs] == [(4, 3), (5, 3)]


def test_dropping_the_reported_loops_leaves_loops_that_cannot_overlap() -> None:
    every = spans((3, 3, 1, 1), (4, 4, 2, 1), (8, 8, 6, 1))
    late = {span for span, _ in overlapping(every)}
    assert overlapping([span for span in every if span not in late]) == []


STAGES = {1, 2, 3, 4}


@pytest.mark.parametrize("rounds", [1, 2, STEP_REVIEW_MAX_ROUNDS])
def test_a_review_that_goes_back_to_an_earlier_stage_works(rounds: int) -> None:
    assert review_problem(StepReview(2, rounds), 3, STAGES) is None


def test_the_rounds_are_limited_to_one_to_the_maximum() -> None:
    limit = f"can send the work back from 1 to {STEP_REVIEW_MAX_ROUNDS} times"
    assert rounds_problem(0) == limit
    assert rounds_problem(STEP_REVIEW_MAX_ROUNDS + 1) == limit
    assert review_problem(StepReview(1, 0), 3, STAGES) == limit
    assert review_problem(StepReview(1, STEP_REVIEW_MAX_ROUNDS + 1), 3, STAGES) == limit


@pytest.mark.parametrize("target", [3, 4])
def test_the_work_can_only_go_back_to_an_earlier_stage(target: int) -> None:
    assert review_problem(StepReview(target, 1), 3, STAGES) == (
        "can only send the work back to an earlier stage"
    )


def test_a_reviewer_in_the_first_stage_has_nowhere_to_send_the_work() -> None:
    assert review_problem(StepReview(1, 1), 1, STAGES) is not None


def test_the_stage_it_goes_back_to_must_have_steps() -> None:
    assert review_problem(StepReview(2, 1), 4, {1, 3, 4}) == (
        "sends the work back to stage 2, which has no steps"
    )
    assert review_problem(StepReview(0, 1), 3, STAGES) == (
        "sends the work back to stage 0, which has no steps"
    )


@pytest.mark.parametrize(
    "raw",
    [None, 2, "2", [], {}, {"send_back_to_stage": 1}, {"max_rounds": 2}],
)
def test_malformed_review_data_reads_as_no_review(raw: object) -> None:
    assert review_from_data(raw) is None


@pytest.mark.parametrize(
    ("stage", "rounds"),
    [(1, 2), ("1", "2"), (1.0, 2.0), (" 1 ", "2")],
)
def test_review_data_may_write_its_numbers_as_text(stage: object, rounds: object) -> None:
    assert review_from_data({"send_back_to_stage": stage, "max_rounds": rounds}) == StepReview(1, 2)


@pytest.mark.parametrize("bad", [True, 1.5, "one", "-1", "", None, [1]])
def test_a_number_that_is_not_a_whole_number_reads_as_no_review(bad: object) -> None:
    assert review_from_data({"send_back_to_stage": bad, "max_rounds": 1}) is None
    assert review_from_data({"send_back_to_stage": 1, "max_rounds": bad}) is None
