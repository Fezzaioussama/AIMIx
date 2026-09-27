"""OpenRouter provider — an OpenAI-compatible endpoint behind a base URL."""

from __future__ import annotations

from openai import OpenAI

from llm.base import LLMProvider, OpenAICompatibleProvider, ProviderConfig
from llm.exceptions import ProviderNotConfigured

NAME = "openrouter"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def build(config: ProviderConfig) -> LLMProvider:
    if not config.api_key:
        raise ProviderNotConfigured("OPEN_ROUTER_KEY is not set.")
    client = OpenAI(
        base_url=config.base_url or DEFAULT_BASE_URL,
        api_key=config.api_key,
        timeout=config.timeout_seconds,
        # No hidden SDK retries: with a long timeout they would multiply the wait,
        # and the documented policy is that failures surface at once.
        max_retries=0,
    )
    return OpenAICompatibleProvider(NAME, client, config)
