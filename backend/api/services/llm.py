"""Builds the configured LLM provider (AGENTS.md §7 Factory).

This is the only module that reads provider configuration out of the
settings; the llm package itself receives plain values (§5 D).
"""

from __future__ import annotations

from api.exceptions import ProviderNotConfigured
from api.services.catalog import default_model_id
from config.settings import get_settings
from llm import exceptions as llm_exceptions
from llm.base import LLMProvider, ProviderConfig
from llm.registry import canonical_name, create_provider


def provider_config(provider: str) -> ProviderConfig:
    settings = get_settings()
    return ProviderConfig(
        api_key=settings.llm_api_keys.get(provider, ""),
        default_model=default_model_id(),
        timeout_seconds=settings.llm_timeout_seconds,
        base_url=settings.llm_base_urls.get(provider) or None,
    )


def get_provider() -> LLMProvider:
    """Return the configured provider, or raise a domain error the API can map."""
    try:
        provider = canonical_name(get_settings().llm_provider)
        return create_provider(provider, provider_config(provider))
    except llm_exceptions.ProviderNotConfigured as cause:
        raise ProviderNotConfigured(str(cause)) from cause
