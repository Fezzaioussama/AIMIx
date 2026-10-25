"""Request contracts, including the model validation that closes the
silent-empty-output bug."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.schemas.chat import ChatRequest
from api.schemas.pipelines import GenerateRequest, PipelineIn, PipelinePatch, RunRequest
from api.services.run_budget import RunBudget


def pipeline(**step: object) -> dict[str, object]:
    return {"name": "P", "steps": [{"order": 1, "prompt": "x", **step}]}


def test_pipeline_rejects_a_model_the_provider_cannot_reach() -> None:
    with pytest.raises(ValidationError, match="Unknown model"):
        PipelineIn.model_validate(pipeline(model="meta-llama/Llama-3-8b-chat-hf"))


def test_pipeline_accepts_a_catalogued_model(default_model: str) -> None:
    assert PipelineIn.model_validate(pipeline(model=default_model)).steps[0].model == default_model


def test_a_step_without_a_stage_runs_in_its_own_stage(default_model: str) -> None:
    body = {"name": "P", "steps": [{"order": 3, "prompt": "x", "model": default_model}]}
    assert PipelineIn.model_validate(body).steps[0].stage == 3


def test_a_step_can_be_titled_and_marked_as_an_output(default_model: str) -> None:
    step = PipelineIn.model_validate(
        pipeline(model=default_model, title="Tweet", is_output=True)
    ).steps[0]
    assert (step.title, step.is_output) == ("Tweet", True)


def test_agent_role_and_tool_policy_are_validated(default_model: str) -> None:
    step = PipelineIn.model_validate(
        pipeline(model=default_model, role="Researcher", allowed_tools=["docs_search"])
    ).steps[0]
    assert (step.role, step.allowed_tools) == ("Researcher", ["docs_search"])
    with pytest.raises(ValidationError, match="unique"):
        PipelineIn.model_validate(
            pipeline(model=default_model, allowed_tools=["docs_search", "docs_search"])
        )
    with pytest.raises(ValidationError):
        PipelineIn.model_validate(pipeline(model=default_model, allowed_tools=[" "]))


def test_a_stage_must_be_positive(default_model: str) -> None:
    with pytest.raises(ValidationError):
        PipelineIn.model_validate(pipeline(model=default_model, stage=0))


def test_a_prompt_must_not_be_blank(default_model: str) -> None:
    with pytest.raises(ValidationError):
        PipelineIn.model_validate(pipeline(model=default_model, prompt="   "))


def test_pipeline_requires_at_least_one_step() -> None:
    with pytest.raises(ValidationError, match="at least one step"):
        PipelineIn.model_validate({"name": "P", "steps": []})


def test_a_patch_may_leave_the_steps_alone() -> None:
    assert PipelinePatch.model_validate({"name": "New"}).steps is None


@pytest.mark.parametrize("payload", [{}, {"prompt": ""}, {"prompt": "   "}])
def test_chat_requires_a_non_blank_prompt(payload: dict) -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(payload)


def test_run_trims_the_text_and_named_values() -> None:
    # Which of the two a run needs depends on the pipeline, so the service checks it.
    body = RunRequest.model_validate({"input": " go ", "inputs": {"topic": " bees "}})
    assert (body.input, body.inputs) == ("go", {"topic": "bees"})
    assert RunRequest.model_validate({}).model_dump() == {
        "input": "",
        "inputs": {},
        "max_cost_usd": None,
        "max_tokens": None,
    }


def test_a_run_may_set_a_cost_and_a_token_limit() -> None:
    body = RunRequest.model_validate({"input": "go", "max_cost_usd": 0.5, "max_tokens": 20_000})
    assert (body.budget.max_cost_usd, body.budget.max_tokens) == (0.5, 20_000)
    assert RunRequest.model_validate({"input": "go"}).budget == RunBudget()


@pytest.mark.parametrize(
    "limits",
    [
        {"max_cost_usd": 0},
        {"max_cost_usd": -1},
        {"max_cost_usd": float("inf")},
        {"max_cost_usd": "a lot"},
        {"max_tokens": 0},
        {"max_tokens": -5},
        {"max_tokens": 1.5},
    ],
)
def test_a_run_refuses_limits_that_cannot_be_met(limits: dict) -> None:
    with pytest.raises(ValidationError):
        RunRequest.model_validate({"input": "go", **limits})


def test_named_inputs_are_validated(default_model: str) -> None:
    body = pipeline(model=default_model)
    body["inputs"] = [{"name": " topic ", "label": "Topic"}]
    field = PipelineIn.model_validate(body).inputs[0]
    assert (field.name, field.label, field.description) == ("topic", "Topic", "")
    assert PipelineIn.model_validate(pipeline(model=default_model)).inputs == []


@pytest.mark.parametrize(
    ("inputs", "problem"),
    [
        ([{"name": "Topic"}], "lowercase letter"),
        ([{"name": "2nd"}], "lowercase letter"),
        ([{"name": "my-topic"}], "lowercase letter"),
        ([{"name": "input"}], "reserved"),
        ([{"name": "x" * 41}], "at most 40"),
        ([{"name": "topic"}, {"name": "topic"}], "unique name"),
        ([{"name": f"field_{n}"} for n in range(21)], "at most 20"),
        ([{"name": "topic", "label": "x" * 101}], "at most 100"),
    ],
)
def test_invalid_named_inputs_are_rejected(
    default_model: str, inputs: list[dict[str, str]], problem: str
) -> None:
    body = pipeline(model=default_model)
    body["inputs"] = inputs
    with pytest.raises(ValidationError, match=problem):
        PipelineIn.model_validate(body)


def test_a_step_can_describe_its_expected_output(default_model: str) -> None:
    step = PipelineIn.model_validate(
        pipeline(model=default_model, expected_output="One tweet")
    ).steps[0]
    assert step.expected_output == "One tweet"
    assert PipelineIn.model_validate(pipeline(model=default_model)).steps[0].expected_output == ""
    with pytest.raises(ValidationError, match="at most 500"):
        PipelineIn.model_validate(pipeline(model=default_model, expected_output="x" * 501))


def test_a_patch_may_leave_the_inputs_alone() -> None:
    assert PipelinePatch.model_validate({"name": "New"}).inputs is None


def test_generate_leaves_the_planner_to_the_callers_default() -> None:
    # The default is per user (Settings page), so the service fills it in.
    assert GenerateRequest.model_validate({"description": "x"}).planner_model is None


def test_generate_rejects_an_unknown_planner_model() -> None:
    with pytest.raises(ValidationError):
        GenerateRequest.model_validate({"description": "x", "planner_model": "stale/model"})
