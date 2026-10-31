"""Speech to text: one recorded clip in, its transcript out (Muse Voice Transcribe).

Meta's batch endpoint takes a WAV clip (mono, 16-bit PCM, 16 or 24 kHz) as a
multipart upload beside a JSON ``request`` part, and answers with the whole
transcript. It is called through the Meta provider's client, so it shares that
client's timeout, the retry policy (llm/retry.py) and the failure contract of
llm/base.py (§5 L): only ``ProviderTimeout`` or ``ProviderRequestError`` escape.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from llm.base import ProviderConfig, normalised_failures
from llm.exceptions import ProviderRequestError
from llm.providers import meta
from llm.retry import SYSTEM_CLOCK, Retrier, RetryClock

#: The provider whose key a transcription spends.
PROVIDER = meta.NAME
TRANSCRIBE_PATH = "/asr/transcribe"


@dataclass(frozen=True)
class Transcript:
    """What one clip said (§7 Value Object)."""

    text: str
    #: How long the clip was, as the provider measured it; None when it did not say.
    duration_ms: int | None


class Transcriber(Protocol):
    """Turns one WAV clip into text; fails as ``ProviderTimeout`` or ``ProviderRequestError``."""

    def transcribe(self, wav: bytes) -> Transcript: ...


class MetaTranscriber:
    """Muse Voice Transcribe's batch endpoint behind our own contract (§7 Adapter).

    ``config.default_model`` is the speech model, e.g. ``muse-voice-transcribe-1.0``.
    """

    def __init__(self, config: ProviderConfig, clock: RetryClock = SYSTEM_CLOCK) -> None:
        self._client = meta.client(config)
        self._config = config
        self._clock = clock

    def transcribe(self, wav: bytes) -> Transcript:
        model = self._config.default_model
        retrier = Retrier(self._config.retry, PROVIDER, model, self._clock)
        with normalised_failures(PROVIDER, model, self._config.timeout_seconds):
            answer = retrier.call(lambda: self._send(wav, model))
        return _transcript(answer)

    def _send(self, wav: bytes, model: str) -> Any:
        # PUSH_TO_TALK: one clip, one speaker, the whole transcript in one answer.
        request = {"mode": "PUSH_TO_TALK", "model": model, "audioEncoding": "WAV"}
        return self._client.post(
            TRANSCRIBE_PATH,
            cast_to=object,
            # The SDK sends a multipart body only when asked, as its own uploads do.
            options={"headers": {"Content-Type": "multipart/form-data"}},
            files=[
                ("request", (None, json.dumps(request).encode(), "application/json")),
                ("audio", ("clip.wav", wav, "audio/wav")),
            ],
        )


def _transcript(answer: Any) -> Transcript:
    text = answer.get("transcript") if isinstance(answer, dict) else None
    if not isinstance(text, str):
        raise ProviderRequestError(f"{PROVIDER} returned no transcript.")
    duration = answer.get("audioDurationMs")
    known = isinstance(duration, int) and not isinstance(duration, bool)
    return Transcript(text.strip(), duration if known else None)
