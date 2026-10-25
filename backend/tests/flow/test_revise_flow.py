"""Revising a pipeline that has conditions and review loops: the change list names
them, a plan the planner returns is sanitised, and a draft is not refused for them."""

from __future__ import annotations

import copy
import json
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.services import pipeline_revision as service
from api.services.llm import LLMProfile
from api.services.pipeline_changes import PipelineChange, diff_pipelines
from tests.conftest import FakeProvider, use_provider
from tests.test_pipeline_changes import pipeline, step, summary

BLOG_ONLY = {"source": "previous_output", "operator": "contains", "value": "blog"}
SEND_BACK = {"send_back_to_stage": 1, "max_rounds": 2}


def test_a_condition_added_to_a_step_is_a_changed_field() -> None:
    original = pipeline(step(1, "Research"), step(2, "Draft"))
    revised = pipeline(step(1, "Research"), step(2, "Draft", condition=BLOG_ONLY))

    assert summary(diff_pipelines(original, revised)) == [
        ("step", "changed", "Draft", 2, ("condition",))
    ]


def test_a_review_added_or_removed_is_a_changed_field() -> None:
    plain = pipeline(step(1, "Draft"), step(2, "QA"))
    reviewing = pipeline(step(1, "Draft"), step(2, "QA", review=SEND_BACK))

    assert summary(diff_pipelines(plain, reviewing)) == [("step", "changed", "QA", 2, ("review",))]
    assert summary(diff_pipelines(reviewing, plain)) == [("step", "changed", "QA", 2, ("review",))]


def test_a_condition_and_a_review_are_listed_last_and_in_that_order() -> None:
    original = pipeline(step(1, "Draft"), step(2, "QA", is_output=False))
    revised = pipeline(
        step(1, "Draft"),
        step(2, "QA", is_output=True, condition=BLOG_ONLY, review=SEND_BACK, prompt="New"),
    )

    assert summary(diff_pipelines(original, revised)) == [
        ("step", "changed", "QA", 2, ("prompt", "is_output", "condition", "review"))
    ]


def test_changing_what_a_condition_compares_with_is_a_change() -> None:
    before = pipeline(step(1, "A"), step(2, "B", condition=BLOG_ONLY))
    after = pipeline(step(1, "A"), step(2, "B", condition={**BLOG_ONLY, "value": "news"}))
    rounds = pipeline(step(1, "A"), step(2, "B", review=SEND_BACK))
    more_rounds = pipeline(step(1, "A"), step(2, "B", review={**SEND_BACK, "max_rounds": 3}))

    assert summary(diff_pipelines(before, after)) == [("step", "changed", "B", 2, ("condition",))]
    assert summary(diff_pipelines(rounds, more_rounds)) == [
        ("step", "changed", "B", 2, ("review",))
    ]


def test_spacing_in_a_condition_and_the_order_of_its_keys_are_not_changes() -> None:
    before = pipeline(step(1, "A"), step(2, "B", condition=BLOG_ONLY))
    after = pipeline(
        step(
            1,
            "A",
        ),
        step(
            2,
            "B",
            condition={"value": " blog ", "operator": "contains", "source": "previous_output"},
        ),
    )

    assert diff_pipelines(before, after) == []


def test_a_step_that_did_not_change_at_all_keeps_its_flow_and_pairs_with_itself() -> None:
    original = pipeline(step(1, "A"), step(2, "B", condition=BLOG_ONLY, review=SEND_BACK))

    assert diff_pipelines(original, copy.deepcopy(original)) == []


def test_a_draft_that_lacks_the_fields_is_not_changed_by_a_plan_that_has_them_empty() -> None:
    draft = pipeline(step(1, "A"))  # saved before conditions and reviews existed
    revised = pipeline(step(1, "A", condition=None, review=None))

    assert diff_pipelines(draft, revised) == []


def planned_steps(model: str) -> list[dict[str, Any]]:
    base = {"role": "", "allowed_tools": None, "is_output": False, "expected_output": ""}
    return [
        {
            **base,
            "order": 1,
            "stage": 1,
            "title": "Draft",
            "prompt": "Write {input}",
            "model": model,
        },
        {
            **base,
            "order": 2,
            "stage": 2,
            "title": "QA",
            "prompt": "Judge {input}",
            "model": model,
            "review": {"send_back_to_stage": 1, "max_rounds": 2},
        },
        {
            **base,
            "order": 3,
            "stage": 3,
            "title": "SEO",
            "prompt": "Optimise {input}",
            "model": model,
            "condition": {"source": "step:9", "operator": "contains", "value": "blog"},
        },
    ]


def test_a_revision_that_adds_a_reviewer_is_listed_and_its_slips_are_set_aside(
    default_model: str,
) -> None:
    draft = pipeline(planned_steps(default_model)[0])
    provider = FakeProvider(
        reply=json.dumps(
            {"name": "Launch kit", "inputs": [], "steps": planned_steps(default_model)}
        )
    )

    revision = service.revise(
        provider,
        LLMProfile("openrouter", default_model),
        service.RevisionRequest(draft, "Add a QA agent that sends the draft back, and an SEO step"),
    )

    qa, seo = revision.pipeline["steps"][1], revision.pipeline["steps"][2]
    assert qa["review"] == {"send_back_to_stage": 1, "max_rounds": 2}
    # The SEO step looked at a step that does not exist: that condition was dropped.
    assert seo["condition"] is None
    assert revision.changes == [
        PipelineChange("step", "added", "QA", 2),
        PipelineChange("step", "added", "SEO", 3),
    ]


def test_a_draft_with_a_condition_and_a_review_can_be_revised_over_http(
    app: FastAPI, auth_client: TestClient, default_model: str
) -> None:
    steps = planned_steps(default_model)[:2]
    steps[0]["condition"] = None
    steps[1]["condition"] = {"source": "previous_output", "operator": "not_empty", "value": ""}
    plan = {"name": "Kit", "inputs": [], "steps": steps}
    use_provider(app, FakeProvider(reply=json.dumps(plan)))

    response = auth_client.post(
        "/api/pipelines/revise",
        json={"pipeline": plan, "instruction": "Keep it as it is"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["changes"] == []
    assert body["revised_pipeline"]["steps"][1]["review"] == {
        "send_back_to_stage": 1,
        "max_rounds": 2,
    }


def test_a_draft_whose_flow_is_not_valid_yet_can_still_be_revised(
    app: FastAPI, auth_client: TestClient, default_model: str
) -> None:
    # The builder may hold a half-finished flow; the planner's answer is cleaned up anyway.
    steps = planned_steps(default_model)
    plan = {"name": "Kit", "inputs": [], "steps": steps}
    use_provider(app, FakeProvider(reply=json.dumps(plan)))

    response = auth_client.post(
        "/api/pipelines/revise", json={"pipeline": plan, "instruction": "Tidy it"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["revised_pipeline"]["steps"][2]["condition"] is None
