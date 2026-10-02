"""Chat streaming boundary: preserve HTTP errors until the first text chunk."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Protocol

from api.exceptions import DomainError, UpstreamResponseInvalid

logger = logging.getLogger(__name__)


class ChatAgent(Protocol):
    def stream(self, prompt: str) -> AsyncIterator[str]: ...


async def stream_reply(agent: ChatAgent, prompt: str) -> AsyncIterator[str]:
    """Pull the first chunk before the endpoint commits a streaming response."""
    stream = agent.stream(prompt)
    try:
        first = await anext(stream)
    except StopAsyncIteration as cause:
        raise UpstreamResponseInvalid("The chat agent returned no reply.") from cause

    async def chunks() -> AsyncIterator[str]:
        yield first
        try:
            async for chunk in stream:
                yield chunk
        except DomainError as cause:
            logger.warning("chat.stream_interrupted error=%s", type(cause).__name__)

    return chunks()
