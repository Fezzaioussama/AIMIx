"""Contract for turning a recorded clip into text."""

from __future__ import annotations

from pydantic import BaseModel


class TranscriptOut(BaseModel):
    """Response of POST /api/voice/transcribe."""

    transcript: str
    #: How long the clip was, as the speech model measured it; null when it did not say.
    duration_ms: int | None
