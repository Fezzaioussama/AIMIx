"""What the planner may propose: conditions and review loops it writes are kept
when they can work and quietly dropped when they cannot, never failing the plan;
and how the planner is told about them."""

from __future__ import annotations

import json
from typing import Any

import pytest

from api.services.pipelines import parse_plan, sanitise_step
from api.services.prompts import pipeline_generation_prompt, pipeline_revision_prompt

BLOG_ONLY = {"source": "previous_output", "operator": "contains", "value": "blog"}
SEND_BACK = {"send_back_to_stage": 2, "max_rounds": 2}
TOPIC = {"name": "topic", "label": "Topic", "description": "What it is about"}


def plan_step(**fields: Any) -> dict[str, Any]:
    return {"prompt": "do {input}", "model": "m", **fields}


def planned(*steps: dict[str, Any], inputs: list[dict[str, str]] | None = None) -> dict[str, Any]:
    raw = json.dumps({"name": "Plan", "inputs": inputs or [], "steps": list(steps)})
    return parse_plan(raw, ["m"])


def flow_of(plan: dict[str, Any]) -> list[tuple[Any, Any]]:
    return [(step["condition"], step["review"]) for step in plan["steps"]]


def test_a_condition_and_a_review_that_can_work_are_kept_as_planned() -> None:
    plan = planned(
        plan_step(),
        plan_step(condition=BLOG_ONLY),
        plan_step(review=SEND_BACK),
    )

    assert flow_of(plan) == [(None, None), (BLOG_ONLY, None), (None, SEND_BACK)]


def test_a_step_without_the_fields_gets_none_for_both() -> None:
    assert flow_of(planned(plan_step())) == [(None, None)]


def test_a_condition_is_tidied_and_loses_a_value_its_operator_ignores() -> None:
    plan = planned(
        plan_step(),
        plan_step(condition={"source": " step:1 ", "operator": "is_empty", "value": "stray"}),
    )

    assert plan["steps"][1]["condition"] == {
        "source": "step:1",
        "operator": "is_empty",
        "value": "",
    }


def test_numbers_the_planner_wrote_as_text_are_read_as_numbers() -> None:
    plan = planned(
        plan_step(),
        plan_step(review={"send_back_to_stage": "1", "max_rounds": "2"}),
        plan_step(condition={"source": "step:1", "operator": "contains", "value": 2024}),
    )

    assert plan["steps"][1]["review"] == {"send_back_to_stage": 1, "max_rounds": 2}
    assert plan["steps"][2]["condition"]["value"] == "2024"


def test_steps_are_numbered_by_position_so_a_condition_can_name_one() -> None:
    plan = planned(
        plan_step(order=7),
        plan_step(order=7),
        plan_step(condition={"source": "step:2", "operator": "not_empty"}),
    )

    assert [step["order"] for step in plan["steps"]] == [1, 2, 3]
    assert plan["steps"][2]["condition"] is not None


def test_a_condition_may_look_at_an_input_the_plan_declares() -> None:
    plan = planned(
        plan_step(),
        plan_step(condition={"source": "input:topic", "operator": "contains", "value": "bees"}),
        inputs=[TOPIC],
    )

    assert plan["steps"][1]["condition"]["source"] == "input:topic"


@pytest.mark.parametrize(
    "condition",
    [
        {"source": "previous_output", "operator": "sounds_like", "value": "x"},
        {"source": "weather:today", "operator": "contains", "value": "x"},
        {"source": "input:ghost", "operator": "contains", "value": "x"},
        {"source": "step:2", "operator": "contains", "value": "x"},
        {"source": "step:3", "operator": "contains", "value": "x"},
        {"source": "step:9", "operator": "contains", "value": "x"},
        {"source": "previous_output", "operator": "contains", "value": "x" * 201},
        {"source": "previous_output", "operator": "contains", "value": ""},
        {"source": "previous_output", "operator": "contains"},
        {"source": "previous_output"},
        {"operator": "contains", "value": "x"},
        "only if it mentions blogs",
        ["previous_output", "contains", "blog"],
        42,
        True,
    ],
)
def test_a_condition_that_cannot_work_is_dropped_and_the_plan_survives(condition: Any) -> None:
    plan = planned(plan_step(), plan_step(condition=condition), plan_step())

    assert [step["condition"] for step in plan["steps"]] == [None, None, None]
    assert len(plan["steps"]) == 3


@pytest.mark.parametrize(
    "review",
    [
        {"send_back_to_stage": 3, "max_rounds": 1},
        {"send_back_to_stage": 4, "max_rounds": 1},
        {"send_back_to_stage": 0, "max_rounds": 1},
        {"send_back_to_stage": 9, "max_rounds": 1},
        {"send_back_to_stage": 1, "max_rounds": 0},
        {"send_back_to_stage": 1, "max_rounds": 6},
        {"send_back_to_stage": 1, "max_rounds": "lots"},
        {"send_back_to_stage": "first", "max_rounds": 1},
        {"send_back_to_stage": 1.5, "max_rounds": 1},
        {"send_back_to_stage": True, "max_rounds": 1},
        {"send_back_to_stage": 1},
        {"max_rounds": 2},
        "send it back twice",
        2,
        [1, 2],
    ],
)
def test_a_review_that_cannot_work_is_dropped_and_the_plan_survives(review: Any) -> None:
    plan = planned(plan_step(), plan_step(), plan_step(review=review))

    assert [step["review"] for step in plan["steps"]] == [None, None, None]


def test_a_review_in_the_first_stage_is_dropped() -> None:
    plan = planned(plan_step(review={"send_back_to_stage": 1, "max_rounds": 1}), plan_step())

    assert flow_of(plan) == [(None, None), (None, None)]


def test_a_review_may_go_back_to_a_stage_planned_with_parallel_steps() -> None:
    plan = planned(
        plan_step(stage=1),
        plan_step(stage=2),
        plan_step(stage=2),
        plan_step(stage=3, review={"send_back_to_stage": 2, "max_rounds": 3}),
    )

    assert plan["steps"][3]["review"] == {"send_back_to_stage": 2, "max_rounds": 3}


def test_of_two_loops_that_share_a_stage_the_later_one_is_dropped() -> None:
    plan = planned(
        plan_step(),
        plan_step(),
        plan_step(review={"send_back_to_stage": 2, "max_rounds": 1}),
        plan_step(),
        plan_step(review={"send_back_to_stage": 3, "max_rounds": 1}),
    )

    kept = [step["review"] for step in plan["steps"]]
    assert kept == [None, None, {"send_back_to_stage": 2, "max_rounds": 1}, None, None]


def test_loops_that_do_not_share_a_stage_are_both_kept() -> None:
    first = {"send_back_to_stage": 1, "max_rounds": 1}
    second = {"send_back_to_stage": 3, "max_rounds": 2}

    plan = planned(plan_step(), plan_step(review=first), plan_step(), plan_step(review=second))

    assert [step["review"] for step in plan["steps"]] == [None, first, None, second]


def test_one_bad_field_does_not_take_the_good_ones_with_it() -> None:
    plan = planned(
        plan_step(),
        plan_step(
            condition={"source": "step:5", "operator": "contains", "value": "x"}, review=SEND_BACK
        ),
        plan_step(condition=BLOG_ONLY),
    )

    assert flow_of(plan) == [(None, None), (None, None), (BLOG_ONLY, None)]


def test_a_template_step_gets_no_condition_and_no_review() -> None:
    step = {"prompt": "p {input}", "title": "T", "role": "R"}

    sanitise_step(step, 1, ["m"], [])

    assert (step["condition"], step["review"]) == (None, None)


def test_the_generation_prompt_tells_the_planner_about_both_fields() -> None:
    prompt = pipeline_generation_prompt("a blog post", ["m"])

    assert '"condition"' in prompt and '"review"' in prompt
    assert '{"source": "previous_output", "operator": "contains", "value": "blog"}' in prompt
    assert '{"send_back_to_stage": 2, "max_rounds": 2}' in prompt
    for operator in ("contains", "not_contains", "equals", "not_equals", "is_empty", "not_empty"):
        assert operator in prompt
    assert '"input:<name>"' in prompt and '"step:<order>"' in prompt
    assert "{feedback}" in prompt
    # The reviewer is told to judge the work; the verdict line is the engine's business.
    assert "verdict line" in prompt and "never write that in the prompt" in prompt
    assert "two review loops must not share a stage" in prompt
    assert "(1 to 5)" in prompt


def test_the_revision_prompt_keeps_the_flow_of_unchanged_steps() -> None:
    prompt = pipeline_revision_prompt({"name": "P", "steps": []}, "Add a QA agent", ["m"])

    assert "is_output, condition and review" in prompt
    assert 'update every "step:<order>" source and every send_back_to_stage' in prompt
    assert "to remove one, set it to null" in prompt
    assert '"condition"' in prompt and '"review"' in prompt
