"""Builds the configured LLM provider (AGENTS.md §7 Factory).

This is the only module that reads provider configuration out of Django
settings; the llm package itself receives plain values (§5 D).
"""

from __future__ import annotations

from django.conf import settings

from api.exceptions import ProviderNotConfigured
from api.services.catalog import default_model_id
from llm import exceptions as llm_exceptions
from llm.base import LLMProvider, ProviderConfig
from llm.registry import canonical_name, create_provider


def provider_config(provider: str) -> ProviderConfig:
    return ProviderConfig(
        api_key=settings.LLM_API_KEYS.get(provider, ""),
        default_model=default_model_id(),
        timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
        base_url=settings.LLM_BASE_URLS.get(provider) or None,
    )


def get_provider() -> LLMProvider:
    """Return the configured provider, or raise a domain error the API can map."""
    try:
        provider = canonical_name(settings.LLM_PROVIDER)
        return create_provider(provider, provider_config(provider))
    except llm_exceptions.ProviderNotConfigured as cause:
        raise ProviderNotConfigured(str(cause)) from cause
