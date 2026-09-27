"""Chat streaming. Wraps the provider so the endpoint only deals with HTTP."""

from __future__ import annotations

import logging
from collections.abc import Iterator

from api.services.errors import as_domain_error
from llm import exceptions as llm_exceptions
from llm.base import LLMProvider

logger = logging.getLogger(__name__)


def stream_reply(provider: LLMProvider, prompt: str) -> Iterator[str]:
    """Yield reply chunks as the provider produces them.

    A failure before the first chunk becomes a domain error, so the endpoint can
    still answer with a proper status. Once streaming has begun the response is
    already committed, so a later failure is logged and the stream ends.
    """
    stream = provider.stream(prompt)
    try:
        first = next(stream)
    except StopIteration:
        return iter(())
    except llm_exceptions.LLMError as cause:
        raise as_domain_error(cause) from cause

    def chunks() -> Iterator[str]:
        yield first
        try:
            yield from stream
        except llm_exceptions.LLMError as cause:
            logger.warning("chat.stream_interrupted error=%s", type(cause).__name__)

    return chunks()
