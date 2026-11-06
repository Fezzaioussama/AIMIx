"""Contracts of Settings → Memory: the person's standing instructions."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.common import Trimmed, UtcDateTime

#: What a request may carry at most; the configured MEMORY_MAX_CHARS is checked after.
MEMORY_REQUEST_MAX_LENGTH = 50_000


class MemoryIn(BaseModel):
    """Body of PUT /api/memory; an empty text forgets the instructions."""

    instructions: Annotated[Trimmed, Field(max_length=MEMORY_REQUEST_MAX_LENGTH)]


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    instructions: str
    #: null until something was saved.
    updated_at: UtcDateTime | None
    #: MEMORY_MAX_CHARS: how long the instructions may be.
    max_chars: int
