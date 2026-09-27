from __future__ import annotations

from pydantic import BaseModel

from api.schemas.common import NonBlank


class ChatRequest(BaseModel):
    """Contract for POST /api/chat."""

    prompt: NonBlank
