"""Request contracts, including the model validation that closes the
silent-empty-output bug."""

from __future__ import annotations

import pytest

from api.serializers import (
    ChatRequestSerializer,
    GeneratePipelineSerializer,
    PipelineSerializer,
    RunPipelineSerializer,
)

pytestmark = pytest.mark.django_db


def test_pipeline_rejects_a_model_the_provider_cannot_reach() -> None:
    serializer = PipelineSerializer(
        data={
            "name": "P",
            "steps": [{"order": 1, "prompt": "x", "model": "meta-llama/Llama-3-8b-chat-hf"}],
        }
    )
    assert not serializer.is_valid()
    assert "steps" in serializer.errors


def test_pipeline_accepts_a_catalogued_model(default_model: str) -> None:
    serializer = PipelineSerializer(
        data={"name": "P", "steps": [{"order": 1, "prompt": "x", "model": default_model}]}
    )
    assert serializer.is_valid(), serializer.errors


def test_pipeline_requires_at_least_one_step() -> None:
    serializer = PipelineSerializer(data={"name": "P", "steps": []})
    assert not serializer.is_valid()


@pytest.mark.parametrize("payload", [{}, {"prompt": ""}, {"prompt": "   "}])
def test_chat_requires_a_non_blank_prompt(payload: dict) -> None:
    assert not ChatRequestSerializer(data=payload).is_valid()


def test_run_requires_a_non_blank_input() -> None:
    assert not RunPipelineSerializer(data={"input": "  "}).is_valid()
    assert RunPipelineSerializer(data={"input": "go"}).is_valid()


def test_generate_defaults_the_planner_model(default_model: str) -> None:
    serializer = GeneratePipelineSerializer(data={"description": "build a thing"})
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["planner_model"] == default_model


def test_generate_rejects_an_unknown_planner_model() -> None:
    serializer = GeneratePipelineSerializer(
        data={"description": "x", "planner_model": "stale/model"}
    )
    assert not serializer.is_valid()
