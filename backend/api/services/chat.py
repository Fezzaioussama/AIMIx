"""Chat streaming boundary: preserve HTTP errors until the first event."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Protocol

from api.exceptions import DomainError, UpstreamResponseInvalid
from api.services.chat_events import ChatEvent

logger = logging.getLogger(__name__)


class ChatAgent(Protocol):
    def stream(self, prompt: str) -> AsyncIterator[ChatEvent]: ...


async def stream_reply(agent: ChatAgent, prompt: str) -> AsyncIterator[ChatEvent]:
    """Pull until the first text before the endpoint commits a streaming response.

    Tool events that happened before it are held back and sent with it, so a
    failure (a refused budget, an unreachable provider) still reaches the client
    as a proper HTTP status instead of a truncated 200 stream.
    """
    stream = agent.stream(prompt)
    pending: list[ChatEvent] = []
    try:
        first = await anext(stream)
        while first.kind != "text":
            pending.append(first)
            first = await anext(stream)
    except StopAsyncIteration as cause:
        raise UpstreamResponseInvalid("The chat agent returned no reply.") from cause

    async def events() -> AsyncIterator[ChatEvent]:
        for event in pending:
            yield event
        yield first
        try:
            async for event in stream:
                yield event
        except DomainError as cause:
            logger.warning("chat.stream_interrupted error=%s", type(cause).__name__)

    return events()
