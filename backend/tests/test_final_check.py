"""The final check every new pipeline ends with: added when the planner left it out,
valid in the plan it joins, and never a second reviewer."""

from __future__ import annotations

import json
from typing import Any

from api.services import pipelines as service
from api.services.final_check import (
    FINAL_CHECK_REQUEST_MAX_CHARS,
    FINAL_CHECK_ROLE,
    FINAL_CHECK_ROUNDS,
    with_final_check,
)
from api.services.llm import LLMProfile
from api.services.pipeline_flow import flow_problems, flow_step
from api.services.plan_questions import Answer
from tests.conftest import FakeProvider

MODEL = "vendor/good"


def plan_of(*steps: dict[str, Any]) -> dict[str, Any]:
    raw = {"name": "Plan", "steps": [{"prompt": "do {input}", "model": MODEL, **s} for s in steps]}
    return service.parse_plan(json.dumps(raw), [MODEL])


def checked(plan: dict[str, Any], description: str = "Write a report", *answers: Answer):
    with_final_check(plan, description, answers, MODEL)
    return plan["steps"][-1]


def test_a_plan_without_a_reviewer_ends_with_the_check() -> None:
    plan = plan_of(
        {"stage": 1, "is_output": False},
        {"stage": 2, "is_output": True},
        {"stage": 2, "is_output": True},
    )

    check = checked(plan)

    assert len(plan["steps"]) == 4
    assert check["order"] == 4 and check["stage"] == 3
    assert check["role"] == FINAL_CHECK_ROLE and check["model"] == MODEL
    assert check["is_output"] is False and check["allowed_tools"] == []
    assert check["review"] == {"send_back_to_stage": 2, "max_rounds": FINAL_CHECK_ROUNDS}
    assert "{input}" in check["prompt"]
    assert flow_problems([], [flow_step(step) for step in plan["steps"]]) == []


def test_without_a_deliverable_the_work_goes_back_to_the_start() -> None:
    check = checked(plan_of({"stage": 1}, {"stage": 2}))

    assert check["review"]["send_back_to_stage"] == 1


def test_a_plan_that_has_a_reviewer_is_left_alone() -> None:
    plan = plan_of(
        {"stage": 1, "is_output": True},
        {"stage": 2, "review": {"send_back_to_stage": 1, "max_rounds": 1}},
    )

    with_final_check(plan, "Write a report", (), MODEL)

    assert len(plan["steps"]) == 2


def test_the_check_quotes_the_request_without_placeholders() -> None:
    answer = Answer("Who reads it?", "The {board}")
    check = checked(plan_of({"is_output": True}), "Report on {topic}", answer)

    assert "Report on (topic)" in check["prompt"]
    assert "Q: Who reads it?\nA: The (board)" in check["prompt"]
    assert check["prompt"].count("{") == 1  # only the {input} the work is placed at


def test_a_long_request_is_cut() -> None:
    check = checked(plan_of({"is_output": True}), "z" * (FINAL_CHECK_REQUEST_MAX_CHARS + 500))

    assert check["prompt"].count("z") == FINAL_CHECK_REQUEST_MAX_CHARS


def test_generation_adds_the_check_the_planner_forgot() -> None:
    reply = {"name": "Translator", "steps": [{"prompt": "Translate {input}", "is_output": True}]}
    provider = FakeProvider(reply=json.dumps(reply))

    plan = service.generate(provider, LLMProfile("openrouter", MODEL), service.PlanRequest("x"))

    assert plan.pipeline is not None
    assert [step["role"] for step in plan.pipeline["steps"]] == ["", FINAL_CHECK_ROLE]
