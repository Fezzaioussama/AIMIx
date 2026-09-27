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
from api.services.prompts import merge_stage_outputs, step_prompt
from llm import exceptions as llm_exceptions
from tests.conftest import FailingProvider, FakeProvider

pytestmark = pytest.mark.django_db


def make_pipeline(
    user, steps: list[tuple[int, str, str]], stages: list[int] | None = None
) -> Pipeline:
    """Steps are ``(order, prompt, model)``; without ``stages`` they form a chain."""
    pipeline = Pipeline.objects.create(user=user, name="Test")
    for index, (order, prompt, model) in enumerate(steps):
        stage = stages[index] if stages else order
        PipelineStep.objects.create(
            pipeline=pipeline, order=order, stage=stage, prompt=prompt, model=model
        )
    return pipeline


class EchoProvider(FakeProvider):
    """Replies with the prompt it received, so each step's output is distinct."""

    def generate(self, prompt: str, model: str | None = None) -> str:
        self.calls.append((prompt, model))
        return f"<{prompt}>"


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


def test_steps_in_one_stage_share_the_input_and_their_outputs_are_merged(
    user, default_model: str
) -> None:
    pipeline = make_pipeline(
        user,
        [
            (1, "a {input}", default_model),
            (2, "b {input}", default_model),
            (3, "c {input}", default_model),
        ],
        stages=[1, 1, 2],
    )

    result = service.run(pipeline, EchoProvider(), "start")

    first, second, merge = result.intermediate_results
    assert [r.stage for r in result.intermediate_results] == [1, 1, 2]
    assert first.input_used == second.input_used == "start"
    assert (first.output, second.output) == ("<a start>", "<b start>")
    assert merge.input_used == merge_stage_outputs([(1, "<a start>"), (2, "<b start>")])
    assert result.final_output == merge.output


def test_a_parallel_last_stage_makes_the_merged_outputs_final(user, default_model: str) -> None:
    pipeline = make_pipeline(
        user, [(1, "a {input}", default_model), (2, "b {input}", default_model)], stages=[1, 1]
    )

    result = service.run(pipeline, EchoProvider(), "x")

    assert result.final_output == merge_stage_outputs([(1, "<a x>"), (2, "<b x>")])


def test_a_failing_parallel_step_fails_the_run(user, default_model: str) -> None:
    pipeline = make_pipeline(
        user, [(1, "a", default_model), (2, "b", default_model)], stages=[1, 1]
    )
    provider = FailingProvider(llm_exceptions.ProviderRequestError("bad"))

    with pytest.raises(ProviderUnavailable):
        service.run(pipeline, provider, "start")


def test_merge_passes_a_single_output_through_and_labels_parallel_ones() -> None:
    assert merge_stage_outputs([(1, "only")]) == "only"
    assert merge_stage_outputs([(2, "b"), (3, "c")]) == (
        "## Output of step 2\n\nb\n\n## Output of step 3\n\nc"
    )


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

    def test_fills_in_a_missing_order_and_stage(self) -> None:
        raw = '{"name": "P", "steps": [{"prompt": "x", "model": "vendor/good"}]}'
        step = service.parse_plan(raw, self.models)["steps"][0]
        assert (step["order"], step["stage"]) == (1, 1)

    def test_keeps_parallel_stages_and_renumbers_repeated_orders(self) -> None:
        raw = (
            '{"name": "P", "steps": ['
            '{"order": 1, "stage": 1, "prompt": "a", "model": "vendor/good"},'
            '{"order": 1, "stage": 1, "prompt": "b", "model": "vendor/good"},'
            '{"order": 2, "stage": 2, "prompt": "c", "model": "vendor/good"}]}'
        )
        steps = service.parse_plan(raw, self.models)["steps"]
        assert [(s["order"], s["stage"]) for s in steps] == [(1, 1), (2, 1), (3, 2)]

    @pytest.mark.parametrize("stage", ["0", '"1"', "true", "-2"])
    def test_an_invalid_stage_falls_back_to_sequential(self, stage: str) -> None:
        step = f'{{"stage": {stage}, "prompt": "x", "model": "vendor/good"}}'
        raw = f'{{"name": "P", "steps": [{step}]}}'
        assert service.parse_plan(raw, self.models)["steps"][0]["stage"] == 1

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
