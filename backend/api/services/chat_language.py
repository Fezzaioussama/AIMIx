"""After a tool's result, the chat model is reminded which language to answer in.

The rule closes the assistant's instructions (``chat_prompts``), yet a result in another
language, such as a French digest or plan, drew French answers to English messages: the
reminder follows the result, where the model reads it last. It rides on the result rather
than in a message of its own, because some models refuse a system message after a tool's,
and only the model's next call sees it: the conversation keeps the tool's own words.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    wrap_model_call,
)
from langchain_core.messages import ToolMessage

from api.services.chat_prompts import language_reminder


def _with_note(message: ToolMessage, note: str) -> ToolMessage:
    """``message`` with ``note`` after its content, be it text or content blocks."""
    content = message.content
    if isinstance(content, str):
        return message.model_copy(update={"content": f"{content}\n\n{note}"})
    return message.model_copy(update={"content": [*content, {"type": "text", "text": note}]})


def answer_in_their_language(prompt: str) -> AgentMiddleware:
    """Middleware adding the reminder for ``prompt``, the person's latest message, to
    the tool result that ends a model call's messages."""
    reminder = language_reminder(prompt)

    @wrap_model_call
    async def remind(
        request: ModelRequest, handler: Callable[[ModelRequest], Awaitable[ModelResponse]]
    ) -> ModelResponse:
        *earlier, last = request.messages
        if isinstance(last, ToolMessage):
            request = request.override(messages=[*earlier, _with_note(last, reminder)])
        return await handler(request)

    return remind
