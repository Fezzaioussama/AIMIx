"""Pipeline endpoints. Each one validates input, calls a service, and shapes the
result — no business logic lives here (AGENTS.md §2)."""

from __future__ import annotations

from dataclasses import asdict

from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from api.http import authenticated_user
from api.models import Pipeline
from api.repositories import pipelines as repository
from api.serializers import (
    GeneratePipelineSerializer,
    PipelineSerializer,
    RunPipelineSerializer,
)
from api.services import pipelines as pipeline_service
from api.services.catalog import available_model_ids
from api.services.llm import get_provider


class PipelineViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PipelineSerializer

    def get_queryset(self) -> QuerySet[Pipeline]:
        return repository.for_user(authenticated_user(self.request))

    def perform_create(self, serializer: BaseSerializer) -> None:
        serializer.save(user=authenticated_user(self.request))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def run_pipeline(request: Request, pipeline_id: int) -> Response:
    payload = RunPipelineSerializer(data=request.data)
    payload.is_valid(raise_exception=True)

    pipeline = repository.get_owned(authenticated_user(request), pipeline_id)
    pipeline_service.ensure_runnable(pipeline)

    result = pipeline_service.run(pipeline, get_provider(), payload.validated_data["input"])
    return Response(asdict(result))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_pipeline(request: Request) -> Response:
    payload = GeneratePipelineSerializer(data=request.data)
    payload.is_valid(raise_exception=True)

    plan = pipeline_service.generate(
        get_provider(),
        payload.validated_data["description"],
        payload.validated_data["planner_model"],
    )
    return Response({"generated_pipeline": plan, "available_models": available_model_ids()})
