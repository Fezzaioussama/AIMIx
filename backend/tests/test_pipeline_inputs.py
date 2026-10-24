"""Named run inputs and expected outputs: binding a run, filling prompts,
sanitising planner output, and the HTTP contract."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.exceptions import ValidationFailed
from api.services import pipelines as service
from api.services.multiagent.contracts import InputField, RunInputs
from api.services.pipeline_inputs import bind_run_inputs, input_name_error
from api.services.prompts import merge_input_values, step_prompt
from tests.conftest import FakeProvider, use_provider
from tests.test_pipeline_service import EchoProvider, make_pipeline

TOPIC = InputField("topic", "Topic", "What to write about")
AUDIENCE = InputField("audience")


def test_input_names_follow_the_placeholder_rule() -> None:
    assert input_name_error("topic_2") is None
    assert input_name_error("input") is not None
    assert input_name_error("Topic") is not None
    assert input_name_error("") is not None


class TestBindRunInputs:
    def test_a_pipeline_without_named_inputs_runs_on_trimmed_text(self) -> None:
        assert bind_run_inputs([], " seed ", {}) == RunInputs("seed")

    def test_one_named_input_passes_through_as_the_first_stage_input(self) -> None:
        assert bind_run_inputs([TOPIC], "", {"topic": " bees "}) == RunInputs(
            "bees", {"topic": "bees"}
        )

    def test_several_named_inputs_are_labelled_for_the_first_stage(self) -> None:
        bound = bind_run_inputs([TOPIC, AUDIENCE], "", {"topic": "bees", "audience": "kids"})
        assert bound.text == "## Topic\n\nbees\n\n## audience\n\nkids"
        assert bound.values == {"topic": "bees", "audience": "kids"}

    @pytest.mark.parametrize(
        ("fields", "text", "values", "problem"),
        [
            ([], "  ", {}, "must not be blank"),
            ([], "seed", {"topic": "bees"}, "has no named inputs"),
            ([TOPIC], "seed", {"topic": "bees"}, "named inputs instead of text: topic"),
            ([TOPIC], "", {"topic": "bees", "tone": "dry"}, "Unknown input 'tone'"),
            ([TOPIC, AUDIENCE], "", {"topic": "bees"}, "Fill in audience"),
            ([TOPIC], "", {"topic": "   "}, "Fill in Topic"),
        ],
    )
    def test_a_run_that_does_not_match_the_declared_inputs_is_rejected(
        self, fields: list[InputField], text: str, values: dict[str, str], problem: str
    ) -> None:
        with pytest.raises(ValidationFailed, match=problem):
            bind_run_inputs(fields, text, values)


class TestStepPrompt:
    def test_named_inputs_are_filled_in_one_pass(self) -> None:
        # A value that looks like a placeholder is inserted as written.
        assert step_prompt("{topic} / {input}", "stage", {"topic": "{input}"}) == "{input} / stage"

    def test_unknown_placeholders_and_other_braces_are_left_alone(self) -> None:
        assert step_prompt('{tone} {"a": 1} {input}', "x", {"topic": "b"}) == '{tone} {"a": 1} x'

    def test_the_first_stage_counts_a_named_input_as_placing_its_input(self) -> None:
        prompt = step_prompt("About {topic}", "bees", {"topic": "bees"}, first_stage=True)
        assert prompt == "About bees"

    def test_a_later_stage_still_receives_the_previous_output(self) -> None:
        prompt = step_prompt("About {topic}", "facts", {"topic": "bees"})
        assert prompt == "About bees\n\nInput: facts"


def test_merge_input_values_passes_one_through_and_labels_several() -> None:
    assert merge_input_values([("Topic", "bees")]) == "bees"
    assert merge_input_values([("Topic", "bees"), ("Tone", "dry")]) == (
        "## Topic\n\nbees\n\n## Tone\n\ndry"
    )


def test_named_inputs_reach_every_stage_of_a_saved_pipeline(default_model: str) -> None:
    pipeline = make_pipeline(
        [(1, "Facts on {topic}", default_model), (2, "Post on {topic}: {input}", default_model)]
    )
    pipeline.inputs = [{"name": "topic", "label": "Topic", "description": ""}]
    provider = EchoProvider()

    result = service.run(pipeline, provider, values={"topic": "bees"})

    assert [prompt for prompt, _ in provider.calls] == [
        "Facts on bees",
        "Post on bees: <Facts on bees>",
    ]
    assert result.intermediate_results[0].input_used == "bees"


# --- Planner output ----------------------------------------------------------


def parse(**plan: object) -> dict[str, Any]:
    """Parse a one-step plan; keyword arguments override its top-level keys."""
    body = {"name": "P", "steps": [{"prompt": "x", "model": "vendor/good"}], **plan}
    return service.parse_plan(json.dumps(body), ["vendor/good"])


def step_with(**fields: object) -> list[dict[str, object]]:
    return [{"prompt": "x", "model": "vendor/good", **fields}]


def test_planned_inputs_are_trimmed() -> None:
    plan = parse(inputs=[{"name": " topic ", "label": " Topic ", "description": 3}])
    assert plan["inputs"] == [{"name": "topic", "label": "Topic", "description": ""}]


def test_planned_inputs_that_cannot_be_saved_are_dropped() -> None:
    inputs = [
        "topic",
        {"label": "No name"},
        {"name": "input"},
        {"name": "Tone"},
        {"name": "topic"},
        {"name": "topic", "label": "Duplicate"},
    ]
    assert parse(inputs=inputs)["inputs"] == [{"name": "topic", "label": "", "description": ""}]


@pytest.mark.parametrize("inputs", [None, "topic", {"name": "topic"}])
def test_planned_inputs_that_are_not_a_list_become_empty(inputs: object) -> None:
    assert parse(inputs=inputs)["inputs"] == []


def test_a_plan_without_inputs_gets_an_empty_list() -> None:
    assert parse()["inputs"] == []


def test_a_planned_expected_output_is_trimmed_clipped_or_defaulted() -> None:
    assert parse(steps=step_with(expected_output=" A tweet "))["steps"][0]["expected_output"] == (
        "A tweet"
    )
    clipped = parse(steps=step_with(expected_output="x" * 600))["steps"][0]["expected_output"]
    assert len(clipped) == 500
    assert parse(steps=step_with(expected_output=5))["steps"][0]["expected_output"] == ""


def test_generate_returns_the_planned_inputs(
    app: FastAPI, auth_client: TestClient, default_model: str
) -> None:
    plan = {
        "name": "Generated",
        "inputs": [{"name": "topic", "label": "Topic", "description": "What to cover"}],
        "steps": [{"prompt": "About {topic}", "model": default_model, "expected_output": "A post"}],
    }
    provider = FakeProvider(reply=json.dumps(plan))
    use_provider(app, provider)

    response = auth_client.post("/api/pipelines/generate", json={"description": "posts"})

    generated = response.json()["generated_pipeline"]
    assert generated["inputs"] == plan["inputs"]
    assert generated["steps"][0]["expected_output"] == "A post"
    planner_prompt = provider.calls[0][0]
    assert '"inputs"' in planner_prompt
    assert '"expected_output"' in planner_prompt


# --- HTTP contract -----------------------------------------------------------


def create(client: TestClient, default_model: str, **overrides: object) -> dict[str, Any]:
    body = {
        "name": "Post",
        "inputs": [{"name": "topic", "label": "Topic", "description": "What to cover"}],
        "steps": [
            {
                "order": 1,
                "prompt": "Write about {topic}",
                "expected_output": "One tweet",
                "model": default_model,
            }
        ],
        **overrides,
    }
    response = client.post("/api/pipelines/", json=body)
    assert response.status_code == 201, response.json()
    return dict(response.json())


def test_inputs_and_expected_outputs_round_trip(
    auth_client: TestClient, default_model: str
) -> None:
    created = create(auth_client, default_model)
    topic = {"name": "topic", "label": "Topic", "description": "What to cover"}
    assert created["inputs"] == [topic]
    assert created["steps"][0]["expected_output"] == "One tweet"

    path = f"/api/pipelines/{created['id']}/"
    assert auth_client.patch(path, json={"name": "Renamed"}).json()["inputs"] == created["inputs"]
    replaced = auth_client.put(
        path, json={"name": "Plain", "steps": [{"order": 1, "prompt": "x", "model": default_model}]}
    )
    # PUT replaces the whole pipeline, so omitted inputs are cleared.
    assert replaced.json()["inputs"] == []


def test_a_pipeline_cannot_declare_the_reserved_input_name(
    auth_client: TestClient, default_model: str
) -> None:
    body = {
        "name": "Bad",
        "inputs": [{"name": "input"}],
        "steps": [{"order": 1, "prompt": "x", "model": default_model}],
    }
    response = auth_client.post("/api/pipelines/", json=body)
    assert response.status_code == 400
    assert "reserved" in response.json()["detail"]


def test_running_with_named_inputs(
    auth_client: TestClient, default_model: str, fake_provider: FakeProvider
) -> None:
    created = create(auth_client, default_model)

    response = auth_client.post(
        f"/api/pipelines/{created['id']}/run", json={"inputs": {"topic": "bees"}}
    )

    assert response.status_code == 200
    assert response.json()["intermediate_results"][0]["input_used"] == "bees"
    assert fake_provider.calls == [("Write about bees", default_model)]


@pytest.mark.parametrize(
    ("body", "problem"),
    [
        ({"inputs": {}}, "Fill in Topic"),
        ({"input": "bees"}, "named inputs instead of text"),
        ({"inputs": {"topic": "bees", "tone": "dry"}}, "Unknown input 'tone'"),
    ],
)
def test_a_run_must_match_the_declared_inputs(
    auth_client: TestClient,
    default_model: str,
    fake_provider: FakeProvider,
    body: dict[str, object],
    problem: str,
) -> None:
    created = create(auth_client, default_model)

    response = auth_client.post(f"/api/pipelines/{created['id']}/run", json=body)

    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"
    assert problem in response.json()["detail"]
    assert fake_provider.calls == []


def test_a_text_pipeline_still_rejects_a_blank_input(
    auth_client: TestClient, default_model: str, fake_provider: FakeProvider
) -> None:
    created = create(auth_client, default_model, inputs=[])

    response = auth_client.post(f"/api/pipelines/{created['id']}/run", json={"input": "  "})

    assert response.status_code == 400
    assert "must not be blank" in response.json()["detail"]
