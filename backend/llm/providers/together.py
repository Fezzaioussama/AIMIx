"""TogetherAI provider through its OpenAI-compatible endpoint."""

from __future__ import annotations

from openai import OpenAI

from llm.base import LLMProvider, OpenAICompatibleProvider, ProviderConfig
from llm.exceptions import ProviderNotConfigured

NAME = "togetherai"
DEFAULT_BASE_URL = "https://api.together.xyz/v1"


def build(config: ProviderConfig) -> LLMProvider:
    if not config.api_key:
        raise ProviderNotConfigured("TOGAI_API_KEY is not set.")
    # max_retries=0 for the same reason as the OpenRouter client.
    client = OpenAI(
        base_url=config.base_url or DEFAULT_BASE_URL,
        api_key=config.api_key,
        timeout=config.timeout_seconds,
        max_retries=0,
    )
    return OpenAICompatibleProvider(NAME, client, config)
