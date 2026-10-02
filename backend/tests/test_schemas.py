"""Request contracts, including the model validation that closes the
silent-empty-output bug."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.schemas.chat import ChatRequest
from api.schemas.pipelines import GenerateRequest, PipelineIn, PipelinePatch, RunRequest


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


def test_run_requires_a_non_blank_input() -> None:
    with pytest.raises(ValidationError):
        RunRequest.model_validate({"input": "  "})
    assert RunRequest.model_validate({"input": " go "}).input == "go"


def test_generate_defaults_the_planner_model(default_model: str) -> None:
    assert GenerateRequest.model_validate({"description": "x"}).planner_model == default_model


def test_generate_rejects_an_unknown_planner_model() -> None:
    with pytest.raises(ValidationError):
        GenerateRequest.model_validate({"description": "x", "planner_model": "stale/model"})
