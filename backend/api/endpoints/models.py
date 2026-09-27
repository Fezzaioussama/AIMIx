"""Model catalogue endpoint — lets the client stay free of a hard-coded list."""

from __future__ import annotations

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from api.services.catalog import available_model_ids, default_model_id


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_models(request: Request) -> Response:
    return Response({"models": available_model_ids(), "default": default_model_id()})
