"""Speech to text: the Meta adapter's request and failure contract, and
POST /api/voice/transcribe. Offline: the openai client and the transcriber are fakes."""

from __future__ import annotations

import io
import json
import wave
from dataclasses import replace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import voice_max_bytes, voice_transcribers
from llm.base import ProviderConfig
from llm.exceptions import ProviderRequestError, ProviderTimeout
from llm.retry import RetryPolicy
from llm.speech import MetaTranscriber, Transcript
from tests.retry_fakes import INSTANT, openai_status, openai_timeout

URL = "/api/voice/transcribe"
NO_RETRIES = replace(INSTANT, retry=RetryPolicy(0, 0.0, 0.0))


def wav(rate: int = 16_000, channels: int = 1, width: int = 2, seconds: float = 0.1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as clip:
        clip.setnchannels(channels)
        clip.setsampwidth(width)
        clip.setframerate(rate)
        clip.writeframes(b"\0" * int(rate * seconds) * channels * width)
    return buffer.getvalue()


class _Client:
    """Stands in for the openai client: each ``post`` plays the next answer."""

    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.calls: list[dict[str, Any]] = []

    def post(self, path: str, **kwargs: Any) -> Any:
        self.calls.append({"path": path, **kwargs})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def transcriber(
    monkeypatch: pytest.MonkeyPatch, client: _Client, config: ProviderConfig = INSTANT
) -> MetaTranscriber:
    monkeypatch.setattr("llm.providers.meta.OpenAI", lambda **kwargs: client)
    return MetaTranscriber(replace(config, default_model="muse-voice-transcribe-1.0"))


def test_a_clip_goes_out_as_multipart_beside_its_request_part(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client({"transcript": " Build me a team. ", "audioDurationMs": 1520, "turns": []})

    assert transcriber(monkeypatch, client).transcribe(b"RIFF") == Transcript(
        "Build me a team.", 1520
    )
    call = client.calls[0]
    assert call["path"] == "/asr/transcribe"
    assert call["options"]["headers"]["Content-Type"] == "multipart/form-data"
    (request_part, (_, request, request_type)), (audio_part, (_, audio, audio_type)) = call["files"]
    assert (request_part, request_type) == ("request", "application/json")
    assert json.loads(request) == {
        "mode": "PUSH_TO_TALK",
        "model": "muse-voice-transcribe-1.0",
        "audioEncoding": "WAV",
    }
    assert (audio_part, audio, audio_type) == ("audio", b"RIFF", "audio/wav")


def test_a_busy_api_is_retried_under_the_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client(openai_status(503), {"transcript": "ok"})

    assert transcriber(monkeypatch, client).transcribe(b"RIFF").text == "ok"
    assert len(client.calls) == 2


@pytest.mark.parametrize(
    ("answer", "error"),
    [
        (openai_status(400), ProviderRequestError),
        (openai_timeout(), ProviderTimeout),
        ({"error": "no transcript"}, ProviderRequestError),
    ],
)
def test_failures_keep_the_provider_contract(
    monkeypatch: pytest.MonkeyPatch, answer: Any, error: type[Exception]
) -> None:
    with pytest.raises(error):
        transcriber(monkeypatch, _Client(answer), NO_RETRIES).transcribe(b"RIFF")


class FakeTranscriber:
    def __init__(self, result: Transcript | Exception) -> None:
        self.result = result
        self.clips: list[bytes] = []

    def transcribe(self, wav: bytes) -> Transcript:
        self.clips.append(wav)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def use_transcriber(app: FastAPI, result: Transcript | Exception) -> FakeTranscriber:
    fake = FakeTranscriber(result)
    app.dependency_overrides[voice_transcribers] = lambda: lambda: fake
    return fake


def post_clip(client: TestClient, clip: bytes) -> httpx.Response:
    return client.post(URL, files={"audio": ("clip.wav", clip, "audio/wav")})


def test_a_clip_comes_back_as_text(app: FastAPI, auth_client: TestClient) -> None:
    fake = use_transcriber(app, Transcript("Research our competitors", 2400))
    clip = wav()

    response = post_clip(auth_client, clip)

    assert response.status_code == 200
    assert response.json() == {"transcript": "Research our competitors", "duration_ms": 2400}
    assert fake.clips == [clip]


@pytest.mark.parametrize(
    "clip",
    [b"", b"not a wav", wav(rate=44_100), wav(channels=2), wav(width=1)],
    ids=["empty", "not-wav", "44khz", "stereo", "8-bit"],
)
def test_a_clip_the_model_cannot_read_is_refused_before_it_is_sent(
    app: FastAPI, auth_client: TestClient, clip: bytes
) -> None:
    fake = use_transcriber(app, Transcript("never", None))

    response = post_clip(auth_client, clip)

    assert (response.status_code, response.json()["error"]) == (400, "validation_error")
    assert fake.clips == []


def test_a_clip_over_the_limit_is_refused(app: FastAPI, auth_client: TestClient) -> None:
    fake = use_transcriber(app, Transcript("never", None))
    app.dependency_overrides[voice_max_bytes] = lambda: 1_000

    response = post_clip(auth_client, wav(seconds=1))

    assert response.status_code == 400
    assert "too long" in response.json()["detail"]
    assert fake.clips == []


def test_without_a_meta_key_the_user_is_sent_to_settings(auth_client: TestClient) -> None:
    # The real factory: the test user saved no Meta key and the server shares none.
    response = post_clip(auth_client, wav())

    assert (response.status_code, response.json()["error"]) == (503, "provider_not_configured")
    assert "Settings" in response.json()["detail"]


def test_a_provider_failure_has_the_standard_error_shape(
    app: FastAPI, auth_client: TestClient
) -> None:
    use_transcriber(app, ProviderRequestError("meta could not answer the request."))

    response = post_clip(auth_client, wav())

    assert (response.status_code, response.json()["error"]) == (502, "provider_unavailable")


def test_transcription_needs_a_signed_in_user(client: TestClient) -> None:
    assert post_clip(client, wav()).status_code == 401
