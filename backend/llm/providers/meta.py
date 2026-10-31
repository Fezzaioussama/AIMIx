"""Meta Model API provider (the Muse models) through its OpenAI-compatible endpoint."""

from __future__ import annotations

from openai import OpenAI

from llm.base import LLMProvider, OpenAICompatibleProvider, ProviderConfig
from llm.exceptions import ProviderNotConfigured

NAME = "meta"
DEFAULT_BASE_URL = "https://api.meta.ai/v1"


def client(config: ProviderConfig) -> OpenAI:
    """The API's client, shared by chat and speech to text (llm/speech.py)."""
    if not config.api_key:
        raise ProviderNotConfigured("META_API_KEY is not set.")
    # max_retries=0 for the same reason as the OpenRouter client: llm/retry.py retries.
    return OpenAI(
        base_url=config.base_url or DEFAULT_BASE_URL,
        api_key=config.api_key,
        timeout=config.timeout_seconds,
        max_retries=0,
    )


def build(config: ProviderConfig) -> LLMProvider:
    return OpenAICompatibleProvider(NAME, client(config), config)
