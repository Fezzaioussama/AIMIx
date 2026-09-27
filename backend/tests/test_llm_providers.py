"""The provider layer: one failure contract, a real timeout, no silent empties.

Before the restructure TogetherAI raised on failure while OpenRouter caught
Exception and returned "" — the §5 L violation these tests lock down.
"""

from __future__ import annotations

from typing import Any

import pytest

from llm.base import OpenAICompatibleProvider, ProviderConfig
from llm.exceptions import ProviderNotConfigured, ProviderRequestError, ProviderTimeout
from llm.providers import openrouter, together
from llm.registry import FACTORIES, canonical_name, create_provider, supported_providers

CONFIG = ProviderConfig(api_key="key", default_model="vendor/model", timeout_seconds=7.5)


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str) -> None:
        self.message = _Message(content)
        self.delta = _Message(content)


class _Response:
    def __init__(self, content: str | None) -> None:
        self.choices = [_Choice(content)] if content is not None else []


class _Completions:
    def __init__(self, result: Any) -> None:
        self._result = result
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _Client:
    def __init__(self, result: Any) -> None:
        self.chat = type("Chat", (), {"completions": _Completions(result)})()


class ReadTimeout(Exception):
    """Stands in for an SDK timeout class — matched by name, as the SDKs differ."""


def build(result: Any) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider("test", _Client(result), CONFIG)


def test_generate_returns_the_message_content() -> None:
    assert build(_Response("hello")).generate("prompt") == "hello"


def test_stream_yields_each_chunk() -> None:
    provider = build([_Response("a"), _Response("b"), _Response(None)])
    assert list(provider.stream("prompt")) == ["a", "b"]


def test_generate_raises_instead_of_returning_empty_on_failure() -> None:
    provider = build(RuntimeError("upstream exploded"))
    with pytest.raises(ProviderRequestError):
        provider.generate("prompt")


def test_stream_raises_instead_of_yielding_nothing_on_failure() -> None:
    provider = build(RuntimeError("upstream exploded"))
    with pytest.raises(ProviderRequestError):
        list(provider.stream("prompt"))


def test_timeouts_map_to_provider_timeout() -> None:
    provider = build(ReadTimeout("too slow"))
    with pytest.raises(ProviderTimeout):
        provider.generate("prompt")


def test_no_choices_is_an_error_not_an_empty_string() -> None:
    with pytest.raises(ProviderRequestError):
        build(_Response(None)).generate("prompt")


def test_missing_model_is_rejected() -> None:
    provider = OpenAICompatibleProvider(
        "test",
        _Client(_Response("x")),
        ProviderConfig(api_key="k", default_model="", timeout_seconds=1.0),
    )
    with pytest.raises(ProviderRequestError):
        provider.generate("prompt", None)


def test_registry_resolves_aliases() -> None:
    assert canonical_name("OpenRouter") == "openrouter"
    assert canonical_name("together_ai") == "togetherai"


def test_registry_rejects_unknown_providers() -> None:
    with pytest.raises(ProviderNotConfigured):
        canonical_name("hal9000")


def test_every_registered_provider_is_reachable_by_name() -> None:
    assert supported_providers() == sorted(FACTORIES)


@pytest.mark.parametrize("module", [openrouter, together])
def test_providers_refuse_to_build_without_a_key(module: Any) -> None:
    with pytest.raises(ProviderNotConfigured):
        module.build(ProviderConfig(api_key="", default_model="m", timeout_seconds=1.0))


def test_openrouter_passes_timeout_and_base_url_to_its_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_openai(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return _Client(_Response("x"))

    monkeypatch.setattr("llm.providers.openrouter.OpenAI", fake_openai)
    create_provider("openrouter", CONFIG)

    assert captured["timeout"] == 7.5
    assert captured["base_url"] == openrouter.DEFAULT_BASE_URL


def test_together_passes_timeout_to_its_client(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_together(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return _Client(_Response("x"))

    monkeypatch.setattr("llm.providers.together.Together", fake_together)
    create_provider("togetherai", CONFIG)

    assert captured["timeout"] == 7.5
