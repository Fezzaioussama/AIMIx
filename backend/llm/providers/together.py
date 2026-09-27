"""TogetherAI provider — its SDK exposes the same chat-completions shape."""

from __future__ import annotations

from together import Together

from llm.base import LLMProvider, OpenAICompatibleProvider, ProviderConfig
from llm.exceptions import ProviderNotConfigured

NAME = "togetherai"


def build(config: ProviderConfig) -> LLMProvider:
    if not config.api_key:
        raise ProviderNotConfigured("TOGAI_API_KEY is not set.")
    # max_retries=0 for the same reason as the OpenRouter client.
    client = Together(api_key=config.api_key, timeout=config.timeout_seconds, max_retries=0)
    return OpenAICompatibleProvider(NAME, client, config)
