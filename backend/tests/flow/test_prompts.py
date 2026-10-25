"""The prompts of review loops: what a reviewer is asked, how a step that was sent
work back is told why, and the placeholders that become reserved."""

from __future__ import annotations

import pytest

from api.services.pipeline_inputs import input_name_error
from api.services.prompts import (
    Feedback,
    PromptFills,
    feedback_block,
    fill_prompt,
    step_agent_system_prompt,
    step_prompt,
)

FEEDBACK = Feedback("Cut the intro.", round=2, rounds=3)


def test_a_reviewer_is_asked_to_end_with_a_verdict_line() -> None:
    prompt = step_agent_system_prompt("QA", has_tools=False, reviewer=True)

    assert "VERDICT: PASS" in prompt and "VERDICT: REVISE" in prompt
    assert prompt.startswith("You are the QA agent in an AIMIx pipeline.")


def test_any_other_step_is_not_asked_for_a_verdict() -> None:
    assert "VERDICT" not in step_agent_system_prompt("Writer", has_tools=True)
    assert "VERDICT" not in step_agent_system_prompt("Writer", has_tools=False, reviewer=False)


def test_the_verdict_rule_comes_after_the_expected_output_and_the_tool_guidance() -> None:
    prompt = step_agent_system_prompt("QA", True, "A short critique", reviewer=True)

    expected, tools, verdict = (
        prompt.index("A short critique"),
        prompt.index("Use your tools"),
        prompt.index("VERDICT: PASS"),
    )
    assert expected < tools < verdict


def test_the_feedback_block_names_the_round_and_holds_the_reviewers_words() -> None:
    assert feedback_block(FEEDBACK) == (
        "Feedback from the reviewer (round 2 of 3):\n\nCut the intro.\n\n"
        "Revise your work to fix what the reviewer found."
    )


def test_feedback_with_nothing_in_it_says_so() -> None:
    block = feedback_block(Feedback("  \n", round=2, rounds=2))

    assert "The reviewer asked for another round but gave no details." in block


def test_a_step_sent_work_back_gets_its_usual_prompt_then_the_feedback() -> None:
    prompt = fill_prompt("Write about {input}", PromptFills("the facts", feedback=FEEDBACK))

    assert prompt == (
        "Write about the facts\n\n"
        "Feedback from the reviewer (round 2 of 3):\n\nCut the intro.\n\n"
        "Revise your work to fix what the reviewer found."
    )


def test_the_input_is_appended_before_the_feedback_when_the_prompt_does_not_place_it() -> None:
    prompt = fill_prompt("Write something", PromptFills("the facts", feedback=FEEDBACK))

    assert prompt.startswith("Write something\n\nInput: the facts\n\nFeedback from the reviewer")


def test_a_prompt_that_places_the_feedback_gets_it_there_and_only_there() -> None:
    prompt = fill_prompt(
        "Reviewer said {feedback}. Redo {input}.", PromptFills("x", feedback=FEEDBACK)
    )

    assert prompt == "Reviewer said Cut the intro.. Redo x."


def test_a_stage_that_was_not_sent_back_to_is_not_told_to_act_on_the_feedback() -> None:
    quiet = Feedback("Cut the intro.", round=2, rounds=3, block=False)

    assert fill_prompt("Merge {input}", PromptFills("x", feedback=quiet)) == "Merge x"
    # ... but it can still place the feedback on purpose.
    assert fill_prompt("Merge {input} ({feedback})", PromptFills("x", feedback=quiet)) == (
        "Merge x (Cut the intro.)"
    )


def test_the_feedback_placeholder_is_empty_while_nothing_was_sent_back() -> None:
    assert fill_prompt("Draft [{feedback}] {input}", PromptFills("x")) == "Draft [] x"


def test_substituted_text_is_never_expanded_again() -> None:
    feedback = Feedback("Use {input} and {topic}", round=2, rounds=2)

    prompt = fill_prompt(
        "{input} / {feedback}", PromptFills("raw {feedback}", {"topic": "T"}, feedback=feedback)
    )

    assert prompt == "raw {feedback} / Use {input} and {topic}"


def test_a_first_stage_that_only_uses_the_feedback_still_gets_its_input() -> None:
    # {feedback} is not one of the run's inputs, so it does not count as placing the first stage's.
    prompt = fill_prompt("Redo it: {feedback}", PromptFills("the run text", first_stage=True))

    assert prompt == "Redo it: \n\nInput: the run text"


def test_a_first_stage_that_uses_a_named_input_has_placed_its_input() -> None:
    prompt = fill_prompt(
        "About {topic}. {feedback}", PromptFills("## Topic\n\nbees", {"topic": "bees"}, True)
    )

    assert prompt == "About bees. "


def test_a_pipeline_that_declared_an_input_named_feedback_before_it_was_reserved_keeps_it() -> None:
    values = {"feedback": "what customers said"}

    plain = fill_prompt("Summarise: {feedback}", PromptFills("## Feedback\n\nx", values, True))
    redone = fill_prompt(
        "Summarise: {feedback}", PromptFills("## Feedback\n\nx", values, True, FEEDBACK)
    )

    # Its own value wins, in the first stage it still counts as the stage's input, and a
    # step that was sent work back is still given the reviewer's feedback.
    assert plain == "Summarise: what customers said"
    assert redone == ("Summarise: what customers said\n\n" + feedback_block(FEEDBACK))


def test_the_older_step_prompt_function_is_the_same_without_feedback() -> None:
    assert step_prompt("{topic} / {input}", "stage", {"topic": "bees"}) == "bees / stage"
    assert step_prompt("About {topic}", "facts", {"topic": "bees"}) == (
        "About bees\n\nInput: facts"
    )
    assert step_prompt("About {topic}", "x", {"topic": "bees"}, first_stage=True) == "About bees"


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("input", "'input' is reserved: {input} is each stage's input."),
        ("feedback", "'feedback' is reserved: {feedback} is a reviewer's feedback on the work."),
    ],
)
def test_the_names_the_engine_fills_cannot_be_declared_as_inputs(name: str, reason: str) -> None:
    assert input_name_error(name) == reason


def test_other_names_are_still_fine() -> None:
    assert input_name_error("feedback_notes") is None
    assert input_name_error("topic") is None
