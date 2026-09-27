"""Pipeline orchestration and planner-response parsing."""

from __future__ import annotations

import pytest

from api.exceptions import (
    ProviderTimedOut,
    ProviderUnavailable,
    UpstreamResponseInvalid,
    ValidationFailed,
)
from api.models import Pipeline, PipelineStep
from api.services import pipelines as service
from api.services.prompts import step_prompt
from llm import exceptions as llm_exceptions
from tests.conftest import FailingProvider, FakeProvider

pytestmark = pytest.mark.django_db


def make_pipeline(user, steps: list[tuple[int, str, str]]) -> Pipeline:
    pipeline = Pipeline.objects.create(user=user, name="Test")
    for order, prompt, model in steps:
        PipelineStep.objects.create(pipeline=pipeline, order=order, prompt=prompt, model=model)
    return pipeline


def test_step_prompt_substitutes_the_placeholder() -> None:
    assert step_prompt("Translate: {input}", "hello") == "Translate: hello"


def test_step_prompt_appends_when_there_is_no_placeholder() -> None:
    assert step_prompt("Summarise", "hello") == "Summarise\n\nInput: hello"


def test_step_prompt_leaves_braces_in_the_input_alone() -> None:
    # str.format would have raised on the braces in the input value.
    assert step_prompt("Echo: {input}", "{not_a_field}") == "Echo: {not_a_field}"


def test_run_feeds_each_output_into_the_next_step(user, default_model: str) -> None:
    pipeline = make_pipeline(
        user, [(1, "one {input}", default_model), (2, "two {input}", default_model)]
    )
    provider = FakeProvider(reply="out")

    result = service.run(pipeline, provider, "start")

    assert [step.step_order for step in result.intermediate_results] == [1, 2]
    assert result.intermediate_results[0].input_used == "start"
    assert result.intermediate_results[1].input_used == "out"
    assert result.final_output == "out"
    assert provider.calls[0][0] == "one start"
    assert provider.calls[1][0] == "two out"


def test_run_translates_a_provider_timeout(user, default_model: str) -> None:
    pipeline = make_pipeline(user, [(1, "p", default_model)])
    provider = FailingProvider(llm_exceptions.ProviderTimeout("slow"))

    with pytest.raises(ProviderTimedOut):
        service.run(pipeline, provider, "start")


def test_run_translates_a_provider_request_error(user, default_model: str) -> None:
    pipeline = make_pipeline(user, [(1, "p", default_model)])
    provider = FailingProvider(llm_exceptions.ProviderRequestError("bad"))

    with pytest.raises(ProviderUnavailable):
        service.run(pipeline, provider, "start")


def test_ensure_runnable_rejects_an_empty_pipeline(user) -> None:
    pipeline = Pipeline.objects.create(user=user, name="Empty")
    with pytest.raises(ValidationFailed):
        service.ensure_runnable(pipeline)


class TestParsePlan:
    models = ["vendor/good", "vendor/also-good"]

    def test_accepts_json_wrapped_in_prose(self) -> None:
        raw = 'Sure! {"name": "P", "steps": [{"order": 1, "prompt": "x", "model": "vendor/good"}]}'
        plan = service.parse_plan(raw, self.models)
        assert plan["name"] == "P"

    def test_replaces_an_unknown_model_with_the_default(self, default_model: str) -> None:
        raw = '{"name": "P", "steps": [{"order": 1, "prompt": "x", "model": "stale/model"}]}'
        plan = service.parse_plan(raw, self.models)
        assert plan["steps"][0]["model"] == default_model

    def test_fills_in_a_missing_order(self) -> None:
        raw = '{"name": "P", "steps": [{"prompt": "x", "model": "vendor/good"}]}'
        assert service.parse_plan(raw, self.models)["steps"][0]["order"] == 1

    @pytest.mark.parametrize(
        "raw",
        [
            "no json at all",
            '{"name": "P"}',
            '{"steps": []}',
            '{"name": "P", "steps": []}',
            '{"name": "P", "steps": ["not an object"]}',
            '{"name": "P", "steps": [{"prompt": "x"}',
        ],
    )
    def test_rejects_unusable_planner_output(self, raw: str) -> None:
        with pytest.raises(UpstreamResponseInvalid):
            service.parse_plan(raw, self.models)


def test_generate_translates_provider_failures() -> None:
    provider = FailingProvider(llm_exceptions.ProviderTimeout("slow"))
    with pytest.raises(ProviderTimedOut):
        service.generate(provider, "build me a thing", "vendor/good")
