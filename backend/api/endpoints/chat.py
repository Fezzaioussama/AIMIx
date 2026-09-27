"""Streaming chat endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.deps import Providers
from api.schemas.chat import ChatRequest
from api.services import chat as chat_service

router = APIRouter(tags=["chat"])


@router.post("/chat", response_class=StreamingResponse)
def chat(body: ChatRequest, providers: Providers) -> StreamingResponse:
    """Hand the prompt to the chat service and stream the reply.

    Errors raised before the first chunk are turned into a proper status by
    api.errors; there is no error handling here.
    """
    chunks = chat_service.stream_reply(providers(), body.prompt)
    return StreamingResponse(chunks, media_type="text/plain; charset=utf-8")
