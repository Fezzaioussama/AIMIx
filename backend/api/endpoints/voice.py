"""Voice endpoint. Validate, call the service, shape the result — no logic
lives here (AGENTS.md §2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile

from api.deps import Transcribers, VoiceMaxBytes
from api.schemas.voice import TranscriptOut
from api.services import voice
from api.throttling import user_rate_limit

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/transcribe", dependencies=[Depends(user_rate_limit)])
def transcribe_clip(
    audio: UploadFile, transcribers: Transcribers, max_bytes: VoiceMaxBytes
) -> TranscriptOut:
    """Turn one recorded clip (WAV) into text with Meta's speech model.

    Nothing is stored: the client puts the text in the message box.
    """
    # One byte past the limit is enough for the service to see the clip is too long,
    # without reading the rest of an oversized upload into memory.
    clip = audio.file.read(max_bytes + 1)
    transcript = voice.transcribe(transcribers, clip, max_bytes)
    return TranscriptOut(transcript=transcript.text, duration_ms=transcript.duration_ms)
