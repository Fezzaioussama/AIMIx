from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from api.schemas.common import NonBlank

#: The longest chat message: a long question with some pasted text.
CHAT_PROMPT_MAX_LENGTH = 100_000


class ChatRequest(BaseModel):
    """Contract for POST /api/chat."""

    prompt: Annotated[NonBlank, Field(max_length=CHAT_PROMPT_MAX_LENGTH)]
