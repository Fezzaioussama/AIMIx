"""Streaming chat endpoint."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from api.deps import Agents, AppSettings
from api.schemas.chat import ChatRequest
from api.services import chat as chat_service
from api.services.chat_conversation import ChatTurn, conversation_of
from api.services.chat_events import ChatEvent, encode
from api.throttling import user_rate_limit

router = APIRouter(tags=["chat"])


async def _lines(events: AsyncIterator[ChatEvent]) -> AsyncIterator[str]:
    async for event in events:
        yield encode(event)


async def _text(events: AsyncIterator[ChatEvent]) -> AsyncIterator[str]:
    """The pre-events contract: the answer as plain text, tool activity omitted."""
    async for event in events:
        if event.kind == "text":
            yield event.text


@router.post("/chat", response_class=StreamingResponse, dependencies=[Depends(user_rate_limit)])
async def chat(
    body: ChatRequest, agents: Agents, request: Request, settings: AppSettings
) -> StreamingResponse:
    """Hand the prompt, the conversation before it and the person's time zone to
    the chat service and stream its events.

    Errors raised before the first text are turned into a proper status by
    api.errors; there is no error handling here. A client that asks for
    ``application/x-ndjson`` gets events; anything else gets the old plain text.
    """
    turns = (ChatTurn(turn.role, turn.content) for turn in body.history)
    conversation = conversation_of(
        body.prompt, turns, body.timezone, settings.chat_history_max_chars
    )
    events = await chat_service.stream_reply(agents(), conversation)
    if "application/x-ndjson" in request.headers.get("accept", ""):
        return StreamingResponse(_lines(events), media_type="application/x-ndjson")
    return StreamingResponse(_text(events), media_type="text/plain")
