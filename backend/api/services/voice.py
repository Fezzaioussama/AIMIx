"""Speech to text for the Missions microphone (AGENTS.md §2: the logic, no HTTP).

The browser records a clip, turns it into the WAV Meta's speech model reads (mono,
16-bit PCM, 16 or 24 kHz) and sends it here; the text goes back to the message
box, where the user reads it before sending anything. The clip is never stored.
"""

from __future__ import annotations

import io
import logging
import time
import wave
from collections.abc import Callable

from api.exceptions import ValidationFailed
from api.services.errors import as_domain_error
from llm import exceptions as llm_exceptions
from llm.speech import Transcriber, Transcript

logger = logging.getLogger(__name__)

#: What the speech model reads: mono 16-bit PCM at one of these rates.
SAMPLE_RATES = (16_000, 24_000)
#: Bytes in a minute of the smaller rate, to say how long a clip may be.
BYTES_PER_MINUTE = 16_000 * 2 * 60


def _check_clip(clip: bytes, max_bytes: int) -> None:
    if not clip:
        raise ValidationFailed("The recording is empty.")
    if len(clip) > max_bytes:
        minutes = max(1, max_bytes // BYTES_PER_MINUTE)
        raise ValidationFailed(f"The recording is too long: keep it under {minutes} minutes.")
    try:
        with wave.open(io.BytesIO(clip), "rb") as audio:
            shape = (audio.getnchannels(), audio.getsampwidth(), audio.getframerate())
    except (wave.Error, EOFError) as cause:
        raise ValidationFailed("The recording is not a WAV file.") from cause
    if shape[:2] != (1, 2) or shape[2] not in SAMPLE_RATES:
        raise ValidationFailed("The recording must be mono 16-bit WAV at 16 or 24 kHz.")


def transcribe(
    make_transcriber: Callable[[], Transcriber], clip: bytes, max_bytes: int
) -> Transcript:
    """The text of one recorded clip. The transcriber is built only once the clip is
    valid, so a missing key is reported for a clip that could have been sent."""
    _check_clip(clip, max_bytes)
    started = time.monotonic()
    try:
        transcript = make_transcriber().transcribe(clip)
    except llm_exceptions.LLMError as cause:
        raise as_domain_error(cause) from cause
    # Sizes and timings only: the words are the user's (§6).
    logger.info(
        "voice.transcribed bytes=%d audio_ms=%s elapsed_ms=%d",
        len(clip),
        transcript.duration_ms,
        (time.monotonic() - started) * 1000,
    )
    return transcript
