"""Runs of conditions and review loops over HTTP: the steps a client polls, the
older runs and results that lack the new fields, and a run that is refused."""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.models import Pipeline, User
from api.repositories import pipelines, runs
from api.repositories.pipelines import PipelineChanges
from tests.conftest import use_pipeline_generator
from tests.flow.fakes import PASS, REVISE, ScriptedAgent, stored_step
from tests.test_agent_tools import chat_tools

BLOG_ONLY = {"source": "previous_output", "operator": "contains", "value": "blog"}
SEND_BACK = {"send_back_to_stage": 2, "max_rounds": 2}


def save(session: Session, owner: User, *steps: dict[str, Any]) -> Pipeline:
    changes = PipelineChanges("Flow", steps=list(steps))
    return pipelines.create_with_steps(session, owner, changes)


def start(client: TestClient, pipeline: Pipeline) -> dict[str, Any]:
    response = client.post(f"/api/pipelines/{pipeline.id}/runs", json={"input": "seed"})
    assert response.status_code == 202, response.text
    polled: dict[str, Any] = client.get(f"/api/runs/{response.json()['id']}").json()
    return polled


def test_a_skipped_step_is_a_step_with_its_own_status_in_the_run(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    use_pipeline_generator(app, ScriptedAgent({"research": ["for the newsletter"]}))
    pipeline = save(
        session,
        user,
        stored_step(1, 1, "research"),
        stored_step(2, 2, "seo", condition=BLOG_ONLY),
    )

    polled = start(auth_client, pipeline)

    assert polled["status"] == "succeeded"
    research, seo = polled["steps"]
    assert (research["status"], seo["status"]) == ("succeeded", "skipped")
    assert (seo["output"], seo["rounds"], seo["verdict"], seo["started_at"]) == ("", 1, None, None)
    assert seo["finished_at"] is not None
    # The run carries the definition it ran, conditions included.
    assert polled["definition"]["steps"][1]["condition"] == BLOG_ONLY
    # The stage that was skipped handed its input on, so that is the run's result.
    assert polled["final_output"] == "for the newsletter"


def test_a_loop_shows_in_the_run_as_rounds_and_the_reviewers_verdict(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    agent = ScriptedAgent({"writer": ["v1", "v2"], "reviewer": [f"Fix X.\n{REVISE}", PASS]})
    use_pipeline_generator(app, agent)
    pipeline = save(
        session,
        user,
        stored_step(1, 1, "research"),
        stored_step(2, 2, "writer"),
        stored_step(3, 3, "reviewer", review=SEND_BACK),
    )

    polled = start(auth_client, pipeline)

    assert polled["status"] == "succeeded"
    assert [(s["rounds"], s["verdict"]) for s in polled["steps"]] == [
        (1, None),
        (2, None),
        (2, "pass"),
    ]
    assert polled["definition"]["steps"][2]["review"] == SEND_BACK
    assert [s["output"] for s in polled["steps"]] == ["out-research", "v2", ""]


def test_a_run_started_through_the_waiting_endpoint_reports_what_was_skipped_and_redone(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    agent = ScriptedAgent({"reviewer": [REVISE, PASS]})
    use_pipeline_generator(app, agent)
    pipeline = save(
        session,
        user,
        stored_step(1, 1, "research"),
        stored_step(2, 2, "seo", condition=BLOG_ONLY),
        stored_step(3, 3, "writer"),
        stored_step(4, 4, "reviewer", review={"send_back_to_stage": 3, "max_rounds": 1}),
    )

    response = auth_client.post(f"/api/pipelines/{pipeline.id}/run", json={"input": "seed"})

    assert response.status_code == 200, response.text
    results = response.json()["intermediate_results"]
    assert [(r["step_order"], r["skipped"], r["rounds"]) for r in results] == [
        (1, False, 1),
        (2, True, 1),
        (3, False, 2),
        (4, False, 2),
    ]
    assert [r["is_output"] for r in results] == [False, False, False, True]


def test_a_run_saved_before_the_new_fields_existed_still_opens(
    auth_client: TestClient, user: User, session: Session
) -> None:
    old = runs.NewRun(
        pipeline_id=None,
        pipeline_name="Old run",
        definition={
            "name": "Old run",
            "inputs": [],
            "steps": [
                {
                    "order": 1,
                    "stage": 1,
                    "title": "Only step",
                    "role": "",
                    "allowed_tools": None,
                    "is_output": True,
                    "expected_output": "",
                    "prompt": "{input}",
                    "model": "m",
                }
            ],
        },
        input_text="seed",
        input_values={},
        steps=[
            {"step_order": 1, "stage": 1, "title": "Only step", "model": "m", "is_output": True}
        ],
    )
    run = runs.create(session, user, old)

    polled = auth_client.get(f"/api/runs/{run.id}").json()

    step = polled["definition"]["steps"][0]
    assert (step["condition"], step["review"]) == (None, None)
    assert (polled["steps"][0]["rounds"], polled["steps"][0]["verdict"]) == (1, None)


def test_a_pipeline_whose_flow_cannot_work_is_not_started(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    # Saving would have refused this; data that got in another way must not run.
    use_pipeline_generator(app, ScriptedAgent())
    broken = {"source": "step:7", "operator": "contains", "value": "x"}
    pipeline = save(session, user, stored_step(1, 1, "a"), stored_step(2, 2, "b", condition=broken))

    response = auth_client.post(f"/api/pipelines/{pipeline.id}/runs", json={"input": "seed"})

    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"
    assert "looks at step 7, which does not run before it" in response.json()["detail"]
    assert auth_client.get("/api/runs").json() == {"items": [], "total": 0}


def test_the_chat_agent_can_read_a_flow_and_run_it(
    app: FastAPI, session: Session, user: User
) -> None:
    agent = ScriptedAgent({"reviewer": [REVISE, PASS]})
    saved = save(
        session,
        user,
        stored_step(1, 1, "research"),
        stored_step(2, 2, "seo", condition=BLOG_ONLY),
        stored_step(3, 3, "writer"),
        stored_step(4, 4, "reviewer", review={"send_back_to_stage": 3, "max_rounds": 1}),
    )
    tools = chat_tools(app, user, agent)

    details = tools["inspect_pipeline"].invoke({"pipeline_id": saved.id})
    result = tools["run_pipeline"].invoke({"pipeline_id": saved.id, "input_text": "hello"})

    assert [(s["condition"], s["review"]) for s in details["steps"]] == [
        (None, None),
        (BLOG_ONLY, None),
        (None, None),
        (None, {"send_back_to_stage": 3, "max_rounds": 1}),
    ]
    steps = result["intermediate_results"]
    assert [(s["skipped"], s["rounds"]) for s in steps] == [
        (False, 1),
        (True, 1),
        (False, 2),
        (False, 2),
    ]
    json.dumps(result)  # what the chat hands the model must serialise
