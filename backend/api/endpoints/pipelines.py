import json

from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.models import Pipeline
from api.serializers import PipelineSerializer
from api.services.llm import get_ai_service
from api.services.pipeline_generation import (
    AVAILABLE_MODELS,
    PIPELINE_GENERATION_PROMPT,
    parse_generated_pipeline,
)
from api.services.pipeline_runner import run_pipeline_steps


class PipelineViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PipelineSerializer

    def get_queryset(self):
        return Pipeline.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def run_pipeline(request, pipeline_id):
    try:
        pipeline = Pipeline.objects.get(id=pipeline_id, user=request.user)
    except Pipeline.DoesNotExist:
        return Response({"error": "Pipeline not found"}, status=404)

    initial_input = request.data.get("input", "")
    if not initial_input:
        return Response({"error": "Initial input is required"}, status=400)

    ai_service, _, error = get_ai_service()
    if error:
        return Response({"error": "AI Service not configured", "details": error}, status=503)

    try:
        final_output, results = run_pipeline_steps(pipeline, ai_service, initial_input)
        return Response(
            {
                "pipeline_name": pipeline.name,
                "final_output": final_output,
                "intermediate_results": results,
            }
        )
    except Exception as exc:
        return Response(
            {"error": f"Pipeline execution failed: {str(exc)}"},
            status=500,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_pipeline(request):
    description = request.data.get("description", "")
    planner_model = request.data.get("planner_model", AVAILABLE_MODELS[0])

    if not description:
        return Response({"error": "Description is required"}, status=400)

    if planner_model not in AVAILABLE_MODELS:
        return Response({"error": f"Invalid planner model. Choose from: {AVAILABLE_MODELS}"}, status=400)

    ai_service, _, error = get_ai_service()
    if error:
        return Response({"error": "AI Service not configured", "details": error}, status=503)

    try:
        response = ai_service.generate_response(
            prompt=PIPELINE_GENERATION_PROMPT + description,
            llm=planner_model,
        )
        pipeline_data, parse_error = parse_generated_pipeline(response)
        if parse_error:
            return Response(
                {
                    "error": parse_error,
                    "raw_response": response,
                },
                status=500,
            )

        return Response(
            {
                "generated_pipeline": pipeline_data,
                "available_models": AVAILABLE_MODELS,
            }
        )
    except json.JSONDecodeError as exc:
        return Response(
            {
                "error": "Failed to parse JSON from AI response",
                "details": str(exc),
                "raw_response": response,
            },
            status=500,
        )
    except Exception as exc:
        return Response({"error": f"Pipeline generation failed: {str(exc)}"}, status=500)
