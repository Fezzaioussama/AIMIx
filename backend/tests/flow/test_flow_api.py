"""Saving conditions and review loops over HTTP: what is stored and sent back, and
the plain 400 that refuses a flow that cannot work."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.models import Pipeline, User
from api.services.catalog import default_model_id
from tests.test_endpoints import make_pipeline

BLOG_ONLY = {"source": "previous_output", "operator": "contains", "value": "blog"}
SEND_BACK = {"send_back_to_stage": 2, "max_rounds": 2}
TOPIC = {"name": "topic", "label": "Topic", "description": ""}


def step(order: int, stage: int, **fields: Any) -> dict[str, Any]:
    return {
        "order": order,
        "stage": stage,
        "title": f"Step {order}",
        "prompt": "do {input}",
        "model": default_model_id(),
        **fields,
    }


def body(*steps: dict[str, Any], inputs: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {"name": "Flow", "inputs": inputs or [], "steps": list(steps)}


def saved(client: TestClient, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/api/pipelines/", json=payload)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def refused(client: TestClient, payload: dict[str, Any]) -> str:
    response = client.post("/api/pipelines/", json=payload)
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "validation_error"
    detail: str = response.json()["detail"]
    return detail


def test_a_condition_and_a_review_are_saved_and_read_back(auth_client: TestClient) -> None:
    created = saved(
        auth_client,
        body(
            step(1, 1),
            step(2, 2, condition=BLOG_ONLY),
            step(3, 3, review=SEND_BACK),
        ),
    )

    fetched = auth_client.get(f"/api/pipelines/{created['id']}/").json()
    first, second, third = fetched["steps"]
    assert (first["condition"], first["review"]) == (None, None)
    assert (second["condition"], second["review"]) == (BLOG_ONLY, None)
    assert (third["condition"], third["review"]) == (None, SEND_BACK)
    assert fetched["steps"] == created["steps"]


def test_a_condition_is_stored_tidy_and_without_a_value_its_operator_ignores(
    auth_client: TestClient,
) -> None:
    created = saved(
        auth_client,
        body(
            step(1, 1),
            step(
                2,
                2,
                condition={"source": " previous_output ", "operator": "is_empty", "value": "x"},
            ),
            step(3, 3, condition={"source": "step:1", "operator": "contains", "value": "  blog  "}),
        ),
    )

    second, third = created["steps"][1], created["steps"][2]
    assert second["condition"] == {"source": "previous_output", "operator": "is_empty", "value": ""}
    assert third["condition"] == {"source": "step:1", "operator": "contains", "value": "blog"}


def test_a_step_may_look_at_a_declared_input_or_an_earlier_step(auth_client: TestClient) -> None:
    created = saved(
        auth_client,
        body(
            step(1, 1),
            step(2, 2, condition={"source": "input:topic", "operator": "not_empty"}),
            step(3, 3, condition={"source": "step:2", "operator": "is_empty"}),
            inputs=[TOPIC],
        ),
    )
    assert created["steps"][1]["condition"]["source"] == "input:topic"


@pytest.mark.parametrize(
    ("condition", "message"),
    [
        (
            {"source": "previous_output", "operator": "sounds_like", "value": "x"},
            "Step 2 (Step 2): its condition compares in a way AIMIx does not know (“sounds_like”).",
        ),
        (
            {"source": "weather", "operator": "contains", "value": "x"},
            "Step 2 (Step 2): its condition needs something to look at: the previous result, "
            "an input or an earlier step.",
        ),
        (
            {"source": "previous_output", "operator": "contains", "value": "x" * 201},
            "Step 2 (Step 2): its condition has text over 200 characters long.",
        ),
        (
            {"source": "previous_output", "operator": "contains", "value": "  "},
            "Step 2 (Step 2): its condition needs the text to compare with.",
        ),
    ],
)
def test_a_condition_that_is_unusable_by_itself_is_a_plain_400(
    auth_client: TestClient, condition: dict[str, str], message: str
) -> None:
    assert refused(auth_client, body(step(1, 1), step(2, 2, condition=condition))) == message


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            "input:audience",
            "Step 2 (Step 2): its condition looks at the input “audience”, "
            "which this pipeline does not have.",
        ),
        (
            "step:2",
            "Step 2 (Step 2): its condition looks at step 2, which does not run before it "
            "(pick a step in an earlier stage).",
        ),
        (
            "step:3",
            "Step 2 (Step 2): its condition looks at step 3, which does not run before it "
            "(pick a step in an earlier stage).",
        ),
        (
            "step:9",
            "Step 2 (Step 2): its condition looks at step 9, which does not run before it "
            "(pick a step in an earlier stage).",
        ),
        (
            "step:one",
            "Step 2 (Step 2): its condition looks at a step by its number, like step:2.",
        ),
    ],
)
def test_a_condition_must_look_at_something_the_pipeline_has(
    auth_client: TestClient, source: str, message: str
) -> None:
    condition = {"source": source, "operator": "contains", "value": "x"}

    assert (
        refused(auth_client, body(step(1, 1), step(2, 2, condition=condition), step(3, 3)))
        == message
    )


def test_a_step_may_not_look_at_a_step_of_its_own_stage(auth_client: TestClient) -> None:
    condition = {"source": "step:1", "operator": "contains", "value": "x"}

    detail = refused(auth_client, body(step(1, 1), step(2, 1, condition=condition)))

    assert "looks at step 1, which does not run before it" in detail


@pytest.mark.parametrize(
    ("review", "message"),
    [
        (
            {"send_back_to_stage": 3, "max_rounds": 1},
            "Step 3 (Step 3): its review loop can only send the work back to an earlier stage.",
        ),
        (
            {"send_back_to_stage": 4, "max_rounds": 1},
            "Step 3 (Step 3): its review loop can only send the work back to an earlier stage.",
        ),
        (
            {"send_back_to_stage": 0, "max_rounds": 1},
            "Step 3 (Step 3): its review loop sends the work back to stage 0, which has no steps.",
        ),
    ],
)
def test_a_review_must_send_the_work_back_to_an_earlier_stage(
    auth_client: TestClient, review: dict[str, int], message: str
) -> None:
    detail = refused(auth_client, body(step(1, 1), step(2, 2), step(3, 3, review=review)))

    assert message in detail


def test_the_stage_a_review_goes_back_to_must_have_steps(auth_client: TestClient) -> None:
    review = {"send_back_to_stage": 2, "max_rounds": 1}

    detail = refused(auth_client, body(step(1, 1), step(2, 3, review=review)))

    assert detail == (
        "Step 2 (Step 2): its review loop sends the work back to stage 2, which has no steps."
    )


@pytest.mark.parametrize("rounds", [0, 6, -1])
def test_a_review_sends_the_work_back_one_to_five_times(
    auth_client: TestClient, rounds: int
) -> None:
    review = {"send_back_to_stage": 1, "max_rounds": rounds}

    detail = refused(auth_client, body(step(1, 1), step(2, 2, review=review)))

    assert detail == ("Step 2 (Step 2): its review loop can send the work back from 1 to 5 times.")


def test_a_reviewer_in_the_first_stage_has_nowhere_to_send_the_work(
    auth_client: TestClient,
) -> None:
    detail = refused(
        auth_client, body(step(1, 1, review={"send_back_to_stage": 1, "max_rounds": 1}))
    )

    assert "its review loop can only send the work back to an earlier stage" in detail


def test_review_loops_may_not_overlap(auth_client: TestClient) -> None:
    inner = {"send_back_to_stage": 2, "max_rounds": 1}
    outer = {"send_back_to_stage": 1, "max_rounds": 1}

    detail = refused(
        auth_client,
        body(step(1, 1), step(2, 2), step(3, 3, review=inner), step(4, 4, review=outer)),
    )

    # The loop that starts later (the inner one) is the one reported.
    assert detail == (
        "Step 3 (Step 3): its review loop shares stages with the one of Step 4 (Step 4). "
        "Review loops cannot overlap."
    )


def test_two_reviewers_in_one_stage_overlap(auth_client: TestClient) -> None:
    review = {"send_back_to_stage": 1, "max_rounds": 1}

    detail = refused(
        auth_client, body(step(1, 1), step(2, 2, review=review), step(3, 2, review=review))
    )

    assert "Review loops cannot overlap" in detail


def test_loops_in_different_stages_are_fine(auth_client: TestClient) -> None:
    saved(
        auth_client,
        body(
            step(1, 1),
            step(2, 2, review={"send_back_to_stage": 1, "max_rounds": 1}),
            step(3, 3),
            step(4, 4, review={"send_back_to_stage": 3, "max_rounds": 2}),
        ),
    )


def test_every_problem_is_told_at_once(auth_client: TestClient) -> None:
    condition = {"source": "input:nope", "operator": "contains", "value": "x"}
    review = {"send_back_to_stage": 9, "max_rounds": 1}

    detail = refused(auth_client, body(step(1, 1, condition=condition), step(2, 2, review=review)))

    assert "Step 1 (Step 1): its condition" in detail
    assert "Step 2 (Step 2): its review loop" in detail


def test_replacing_a_pipeline_checks_the_flow_too(
    auth_client: TestClient, user: User, session: Session
) -> None:
    pipeline = make_pipeline(session, user, "Mine", steps=2)
    condition = {"source": "step:5", "operator": "contains", "value": "x"}

    response = auth_client.put(
        f"/api/pipelines/{pipeline.id}/", json=body(step(1, 1), step(2, 2, condition=condition))
    )

    assert response.status_code == 400
    assert "looks at step 5" in response.json()["detail"]
    kept = auth_client.get(f"/api/pipelines/{pipeline.id}/").json()
    assert [item["condition"] for item in kept["steps"]] == [None, None]


def test_patching_the_steps_checks_them_against_the_inputs_it_keeps(
    auth_client: TestClient,
) -> None:
    created = saved(auth_client, body(step(1, 1), step(2, 2), inputs=[TOPIC]))
    path = f"/api/pipelines/{created['id']}/"
    uses_topic = {"source": "input:topic", "operator": "not_empty"}

    patched = auth_client.patch(
        path, json={"steps": [step(1, 1), step(2, 2, condition=uses_topic)]}
    )
    assert patched.status_code == 200
    assert patched.json()["steps"][1]["condition"] == {**uses_topic, "value": ""}

    uses_missing = {"source": "input:audience", "operator": "not_empty"}
    wrong = auth_client.patch(
        path, json={"steps": [step(1, 1), step(2, 2, condition=uses_missing)]}
    )
    assert wrong.status_code == 400


def test_removing_an_input_a_condition_still_uses_is_refused_and_changes_nothing(
    auth_client: TestClient,
) -> None:
    uses_topic = {"source": "input:topic", "operator": "not_empty"}
    created = saved(auth_client, body(step(1, 1), step(2, 2, condition=uses_topic), inputs=[TOPIC]))
    path = f"/api/pipelines/{created['id']}/"

    response = auth_client.patch(path, json={"inputs": []})

    assert response.status_code == 400
    assert (
        "looks at the input “topic”, which this pipeline does not have" in response.json()["detail"]
    )
    assert [item["name"] for item in auth_client.get(path).json()["inputs"]] == ["topic"]
    # Renaming, and changing only the inputs a condition does not use, are fine.
    assert auth_client.patch(path, json={"name": "Renamed"}).status_code == 200
    other = [TOPIC, {"name": "tone", "label": "", "description": ""}]
    assert auth_client.patch(path, json={"inputs": other}).status_code == 200


def test_feedback_is_a_reserved_input_name(auth_client: TestClient) -> None:
    detail = refused(
        auth_client,
        body(step(1, 1), inputs=[{"name": "feedback", "label": "", "description": ""}]),
    )

    assert "'feedback' is reserved" in detail


def test_a_pipeline_saved_before_the_new_fields_still_lists_and_opens(
    auth_client: TestClient, user: User, session: Session
) -> None:
    pipeline = make_pipeline(session, user, "Old one", steps=2)

    listed = auth_client.get("/api/pipelines/").json()

    assert [(s["condition"], s["review"]) for s in listed[0]["steps"]] == [(None, None)] * 2
    assert isinstance(pipeline, Pipeline)
