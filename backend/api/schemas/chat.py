from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from api.models import TIMEZONE_MAX_LENGTH
from api.schemas.common import NonBlank

#: The longest chat message: a long question with some pasted text.
CHAT_PROMPT_MAX_LENGTH = 100_000
#: The most earlier messages one request may carry; of those, the assistant reads the
#: newest that fit in CHAT_HISTORY_MAX_CHARS.
CHAT_HISTORY_MAX_TURNS = 200


class ChatTurnIn(BaseModel):
    """One earlier message of the conversation, as the chat screen showed it."""

    role: Literal["user", "assistant"]
    content: Annotated[str, Field(max_length=CHAT_PROMPT_MAX_LENGTH)]


class ChatRequest(BaseModel):
    """Contract for POST /api/chat."""

    prompt: Annotated[NonBlank, Field(max_length=CHAT_PROMPT_MAX_LENGTH)]
    #: What was said before the prompt, oldest first.
    history: Annotated[list[ChatTurnIn], Field(max_length=CHAT_HISTORY_MAX_TURNS)] = Field(
        default_factory=list
    )
    #: The browser's IANA time zone ("Europe/Paris"); one the server does not know is ignored.
    timezone: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=TIMEZONE_MAX_LENGTH)]
        | None
    ) = None
