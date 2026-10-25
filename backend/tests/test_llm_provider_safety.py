"""What the provider layer lets out: never the key, never the provider's own
words about the account, and the planner's calls stay bounded."""

from __future__ import annotations

import logging
from typing import Any

import httpx2
import openai
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import provider_factory
from api.services import llm as llm_service
from api.services.llm import LLMProfile, get_planner_provider, provider_config
from llm.base import OpenAICompatibleProvider, ProviderConfig
from llm.exceptions import ProviderRequestError
from tests.conftest import TEST_SETTINGS, use_provider
from tests.retry_fakes import URL
from tests.test_llm_providers import CONFIG, _Client, _Response

KEY = "sk-or-v1-0123456789abcdef"
#: What a provider may answer with: the account's state, and part of the key.
UPSTREAM = f"Insufficient credits: this key ({KEY[:12]}...) has $0.01 left"


def payment_required() -> openai.APIStatusError:
    """The SDK's error for a 402 whose message carries the provider's own words."""
    response = httpx2.Response(402, request=httpx2.Request("POST", URL))
    return openai.APIStatusError(UPSTREAM, response=response, body=None)


def test_a_provider_config_never_shows_its_key() -> None:
    config = ProviderConfig(api_key=KEY, default_model="vendor/model", timeout_seconds=1.0)

    assert KEY not in repr(config)
    assert KEY not in str(config)
    assert "vendor/model" in repr(config)


def test_a_rejected_call_is_reported_without_the_providers_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = OpenAICompatibleProvider("test", _Client(payment_required()), CONFIG)

    with (
        caplog.at_level(logging.WARNING, logger="llm.base"),
        pytest.raises(ProviderRequestError) as raised,
    ):
        provider.generate("a prompt with user data")

    assert str(raised.value) == "test could not answer the request."
    assert "credits" not in str(raised.value) and KEY[:12] not in str(raised.value)
    # The log says which call failed and how, never what it said or was sent.
    logged = caplog.text
    assert "error=APIStatusError status=402" in logged
    assert "credits" not in logged and KEY[:12] not in logged
    assert "user data" not in logged


def test_the_planner_endpoints_answer_with_the_generic_message(
    app: FastAPI, auth_client: TestClient
) -> None:
    provider = OpenAICompatibleProvider("openrouter", _Client(payment_required()), CONFIG)
    use_provider(app, provider)

    response = auth_client.post("/api/pipelines/generate", json={"description": "Plan it"})

    assert response.status_code == 502
    assert response.json() == {
        "error": "provider_unavailable",
        "detail": "openrouter could not answer the request.",
    }


def test_a_bounded_provider_asks_for_at_most_that_many_tokens() -> None:
    bounded = ProviderConfig(
        api_key="k", default_model="m", timeout_seconds=1.0, max_output_tokens=900
    )
    client = _Client(_Response("ok"))
    OpenAICompatibleProvider("test", client, bounded).generate("hi")
    assert client.chat.completions.kwargs["max_tokens"] == 900

    unbounded = _Client(_Response("ok"))
    OpenAICompatibleProvider("test", unbounded, CONFIG).generate("hi")
    assert "max_tokens" not in unbounded.chat.completions.kwargs


def test_the_planner_gets_its_own_timeout_and_output_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: list[ProviderConfig] = []

    def capture(name: str, config: ProviderConfig) -> Any:
        built.append(config)
        return object()

    monkeypatch.setattr(llm_service, "create_provider", capture)
    profile = LLMProfile("openrouter", "deepseek/deepseek-v4-flash", api_key="user-key")

    get_planner_provider(profile)

    # The planner endpoints get this provider (tests swap the factory out).
    assert provider_factory(profile).func is get_planner_provider  # type: ignore[attr-defined]
    assert built[0].timeout_seconds == TEST_SETTINGS.llm_planner_timeout_seconds
    assert built[0].max_output_tokens == TEST_SETTINGS.llm_planner_max_output_tokens
    # Every other call keeps the long timeout and no bound of its own.
    general = provider_config(profile)
    assert (general.timeout_seconds, general.max_output_tokens) == (1.0, None)


def test_the_planner_bounds_have_safe_defaults() -> None:
    from config.settings import Settings

    defaults = Settings(_env_file=None)  # type: ignore[call-arg]
    assert defaults.llm_planner_timeout_seconds < defaults.llm_timeout_seconds
    assert defaults.llm_planner_max_output_tokens == 32_000
