"""The provider contract and the one implementation both providers share.

OpenRouter and TogetherAI both expose an OpenAI-compatible
``chat.completions.create``, so the transport lives here once (AGENTS.md §3)
and each provider module only supplies a configured client.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from llm.exceptions import ProviderRequestError, ProviderTimeout

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderConfig:
    """Everything a provider needs, passed in rather than read from the
    environment, so the layer stays framework-agnostic and testable (§5 D)."""

    api_key: str
    default_model: str
    timeout_seconds: float
    base_url: str | None = None


@runtime_checkable
class LLMProvider(Protocol):
    """Narrow contract every provider honours, including its failure modes (§5 L).

    ``generate`` and ``stream`` raise ``ProviderTimeout`` or
    ``ProviderRequestError``. Neither ever returns an empty string to signal
    failure — an empty result means the model genuinely produced nothing.
    """

    name: str

    def generate(self, prompt: str, model: str | None = None) -> str: ...

    def stream(self, prompt: str, model: str | None = None) -> Iterator[str]: ...


def _is_timeout(error: Exception) -> bool:
    """SDKs surface timeouts under different class names; match on the name so
    this layer does not depend on either SDK's exception hierarchy."""
    return "timeout" in type(error).__name__.lower()


class OpenAICompatibleProvider:
    """Shared provider implementation over an OpenAI-shaped chat client."""

    def __init__(self, name: str, client: Any, config: ProviderConfig) -> None:
        self.name = name
        self._client = client
        self._config = config

    def _resolve_model(self, model: str | None) -> str:
        chosen = (model or self._config.default_model or "").strip()
        if not chosen:
            raise ProviderRequestError("No model id was supplied and no default is configured.")
        return chosen

    def _create(self, prompt: str, model: str | None, *, stream: bool) -> Any:
        resolved = self._resolve_model(model)
        try:
            return self._client.chat.completions.create(
                model=resolved,
                messages=[{"role": "user", "content": prompt}],
                stream=stream,
            )
        except Exception as cause:
            # Normalised so every provider fails the same way (§5 L). The
            # prompt is deliberately never logged (§6 observability).
            logger.warning(
                "llm.request_failed provider=%s model=%s error=%s",
                self.name,
                resolved,
                type(cause).__name__,
            )
            if _is_timeout(cause):
                raise ProviderTimeout(
                    f"{self.name} did not respond within {self._config.timeout_seconds:g}s."
                ) from cause
            raise ProviderRequestError(f"{self.name} rejected the request: {cause}") from cause

    def generate(self, prompt: str, model: str | None = None) -> str:
        response = self._create(prompt, model, stream=False)
        choices = getattr(response, "choices", None)
        if not choices:
            raise ProviderRequestError(f"{self.name} returned no choices.")
        return choices[0].message.content or ""

    def stream(self, prompt: str, model: str | None = None) -> Iterator[str]:
        for chunk in self._create(prompt, model, stream=True):
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            content = getattr(choices[0].delta, "content", None)
            if content:
                yield content
