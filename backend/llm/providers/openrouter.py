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
        # No hidden SDK retries: the SDK would also retry timeouts, 409 and
        # every 5xx. OpenAICompatibleProvider applies the policy in llm/retry.py.
        max_retries=0,
    )
    return OpenAICompatibleProvider(NAME, client, config)
