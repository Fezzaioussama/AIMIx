"""The direct provider (pipeline planning) retries under the configured policy,
and the retry settings travel from the environment to both call paths.

Fake SDK clients only: nothing reaches the network, and no wait is real.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from pydantic import ValidationError

from api.services.llm import LLMProfile, provider_config
from config.settings import Settings, pin_settings
from llm.agent_models import create_agent_model
from llm.base import OpenAICompatibleProvider
from llm.exceptions import ProviderRequestError, ProviderTimeout
from llm.registry import create_provider
from llm.retry import RetryPolicy
from tests.conftest import TEST_SETTINGS
from tests.retry_fakes import (
    CONFIG,
    INSTANT,
    SECRET_KEY,
    FakeClock,
    openai_connection_error,
    openai_status,
    openai_timeout,
)


class _Piece:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str | None) -> None:
        self.message = self.delta = _Piece(content)


class _Chunk:
    """A completion, or one streamed chunk of it: both carry ``choices``."""

    def __init__(self, content: str | None) -> None:
        self.choices = [_Choice(content)]


class _Completions:
    """``create`` follows a script: raise the next error, or return the next value."""

    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def create(self, **kwargs: Any) -> Any:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _Client:
    def __init__(self, *outcomes: Any) -> None:
        self.completions = _Completions(*outcomes)
        self.chat = type("Chat", (), {"completions": self.completions})()


def chunks(*pieces: str | None, error: BaseException | None = None) -> Iterator[_Chunk]:
    yield from (_Chunk(piece) for piece in pieces)
    if error is not None:
        raise error


def provider(client: _Client, clock: FakeClock) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider("openrouter", client, CONFIG, clock.retry_clock())


def test_generate_retries_transient_failures_then_answers() -> None:
    clock = FakeClock()
    client = _Client(openai_status(429), openai_status(503), _Chunk("hello"))
    assert provider(client, clock).generate("prompt") == "hello"
    assert (client.completions.calls, clock.waits) == (3, [1.0, 2.0])


def test_generate_raises_the_usual_error_once_retries_run_out() -> None:
    errors = [openai_status(503) for _ in range(3)]
    client = _Client(*errors)
    with pytest.raises(ProviderRequestError) as raised:
        provider(client, FakeClock()).generate("prompt")
    assert raised.value.__cause__ is errors[-1]
    assert client.completions.calls == 3


@pytest.mark.parametrize(
    ("error", "expected"),
    [(openai_timeout(), ProviderTimeout), (openai_status(400), ProviderRequestError)],
    ids=["timeout", "bad-request"],
)
def test_generate_does_not_retry_a_timeout_or_a_rejected_request(
    error: Exception, expected: type[Exception]
) -> None:
    client = _Client(error)
    with pytest.raises(expected):
        provider(client, FakeClock()).generate("prompt")
    assert client.completions.calls == 1


def test_stream_retries_a_connection_dropped_before_any_text() -> None:
    dropped = chunks(None, "", error=openai_connection_error())  # role-only chunks, then a drop
    client = _Client(dropped, chunks("Hel", "lo"))
    assert "".join(provider(client, FakeClock()).stream("prompt")) == "Hello"
    assert client.completions.calls == 2


def test_stream_never_replays_text_already_sent() -> None:
    client = _Client(chunks("Hel", error=openai_connection_error()), chunks("Hello"))
    received: list[str] = []
    with pytest.raises(ProviderRequestError):
        received.extend(provider(client, FakeClock()).stream("prompt"))
    assert (received, client.completions.calls) == (["Hel"], 1)


def test_retries_are_logged_without_the_prompt_or_the_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _Client(openai_status(502), _Chunk("hello"))
    with caplog.at_level(logging.WARNING):
        provider(client, FakeClock()).generate("my confidential prompt")
    assert "llm.retry provider=openrouter model=vendor/model attempt=1/3" in caplog.text
    assert "confidential" not in caplog.text
    assert SECRET_KEY not in caplog.text


def test_retry_settings_have_the_documented_defaults() -> None:
    defaults = {
        "llm_max_retries": 2,
        "llm_retry_base_delay_seconds": 1.0,
        "llm_retry_max_delay_seconds": 20.0,
    }
    assert {name: Settings.model_fields[name].default for name in defaults} == defaults


@pytest.mark.parametrize(
    "invalid",
    [
        {"LLM_MAX_RETRIES": "-1"},
        {"LLM_MAX_RETRIES": "11"},
        {"LLM_RETRY_BASE_DELAY_SECONDS": "-1"},
        {"LLM_RETRY_MAX_DELAY_SECONDS": "-1"},
    ],
)
def test_retry_settings_are_bounded(invalid: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **invalid)  # type: ignore[arg-type]


def test_retry_settings_reach_the_provider_config() -> None:
    values = {"llm_max_retries": 3, "llm_retry_base_delay_seconds": 0.5}
    pin_settings(TEST_SETTINGS.model_copy(update={**values, "llm_retry_max_delay_seconds": 7.0}))
    try:
        config = provider_config(LLMProfile("openrouter", "vendor/model", api_key="saved-key"))
    finally:
        pin_settings(TEST_SETTINGS)
    assert config.retry == RetryPolicy(3, 0.5, 7.0)


@pytest.mark.parametrize(
    ("provider_name", "module"), [("openrouter", "openrouter"), ("togetherai", "together")]
)
def test_the_config_policy_reaches_both_call_paths(
    monkeypatch: pytest.MonkeyPatch, provider_name: str, module: str
) -> None:
    model: Any = create_agent_model(provider_name, CONFIG)
    assert (model.retrier.policy, model.retrier.provider) == (CONFIG.retry, provider_name)
    assert model.retrier.model == CONFIG.default_model

    built: dict[str, Any] = {}
    client = _Client(openai_status(503), openai_status(503), _Chunk("planned"))

    def fake_openai(**kwargs: Any) -> _Client:
        built.update(kwargs)
        return client

    monkeypatch.setattr(f"llm.providers.{module}.OpenAI", fake_openai)
    assert create_provider(provider_name, INSTANT).generate("plan") == "planned"
    assert (built["max_retries"], client.completions.calls) == (0, 3)
