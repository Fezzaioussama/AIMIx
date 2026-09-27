from __future__ import annotations

from typing import Any

from rest_framework import serializers

from api.models import Pipeline, PipelineStep
from api.services.catalog import available_model_ids, default_model_id


def _validate_model_id(value: str) -> None:
    """Reject model ids the provider layer does not know about.

    Previously ``PipelineStep.model`` was an unvalidated CharField, so a stale
    id was stored happily and only failed later at run time — as an empty
    result rather than an error.
    """
    allowed = available_model_ids()
    if value not in allowed:
        raise serializers.ValidationError(
            f"Unknown model '{value}'. Choose one of: {', '.join(allowed)}."
        )


class PipelineStepSerializer(serializers.ModelSerializer):
    model = serializers.CharField(validators=[_validate_model_id])

    class Meta:
        model = PipelineStep
        fields = ("id", "order", "prompt", "model")


class PipelineSerializer(serializers.ModelSerializer):
    steps = PipelineStepSerializer(many=True)

    class Meta:
        model = Pipeline
        fields = ("id", "name", "user", "created_at", "steps")
        read_only_fields = ("user", "created_at")

    def validate_steps(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not value:
            raise serializers.ValidationError("A pipeline needs at least one step.")
        return value

    def create(self, validated_data: dict[str, Any]) -> Pipeline:
        from api.repositories import pipelines as repository

        steps = validated_data.pop("steps")
        return repository.create_with_steps(**validated_data, steps=steps)

    def update(self, instance: Pipeline, validated_data: dict[str, Any]) -> Pipeline:
        from api.repositories import pipelines as repository

        steps = validated_data.pop("steps", None)
        return repository.replace_steps(instance, validated_data.get("name"), steps)


class RunPipelineSerializer(serializers.Serializer):
    """Contract for POST /api/pipelines/<id>/run."""

    input = serializers.CharField(trim_whitespace=True, allow_blank=False)


class GeneratePipelineSerializer(serializers.Serializer):
    """Contract for POST /api/pipelines/generate."""

    description = serializers.CharField(trim_whitespace=True, allow_blank=False)
    planner_model = serializers.CharField(required=False, validators=[_validate_model_id])

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs.setdefault("planner_model", default_model_id())
        return attrs
