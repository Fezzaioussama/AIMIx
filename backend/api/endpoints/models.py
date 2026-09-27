from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from api.services.pipeline_generation import AVAILABLE_MODELS, DEFAULT_PIPELINE_MODEL


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_models(request: Request) -> Response:
    """Expose the model ids the pipeline services accept, so the client never
    hard-codes its own copy of the list (single source of truth)."""
    return Response({"models": AVAILABLE_MODELS, "default": DEFAULT_PIPELINE_MODEL})
