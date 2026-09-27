"""Streaming chat endpoint."""

from __future__ import annotations

from django.http import StreamingHttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request

from api.serializers import ChatRequestSerializer
from api.services import chat as chat_service
from api.services.llm import get_provider


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def chat_view(request: Request) -> StreamingHttpResponse:
    """Validate, then hand the prompt to the chat service and stream the reply.

    Errors raised before the first chunk are turned into a proper status by
    api.errors; there is no error handling here.
    """
    payload = ChatRequestSerializer(data=request.data)
    payload.is_valid(raise_exception=True)

    provider = get_provider()
    chunks = chat_service.stream_reply(provider, payload.validated_data["prompt"])
    return StreamingHttpResponse(chunks, content_type="text/plain; charset=utf-8")
