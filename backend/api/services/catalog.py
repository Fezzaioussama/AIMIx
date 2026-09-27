"""Which model ids this deployment accepts.

Derived from the configured provider's catalogue, so the list the API validates
against, the list it serves to clients, and the list the provider can actually
reach are one and the same (AGENTS.md §3).
"""

from __future__ import annotations

from django.conf import settings

from llm.catalog import CATALOGS, ModelCatalog
from llm.registry import canonical_name


def _catalog() -> type[ModelCatalog]:
    provider = canonical_name(settings.LLM_PROVIDER)
    return CATALOGS[provider]


def available_model_ids() -> list[str]:
    """Model ids the configured provider exposes, default first."""
    ids = _catalog().ids()
    default = default_model_id()
    if default in ids:
        return [default, *(model_id for model_id in ids if model_id != default)]
    return ids


def default_model_id() -> str:
    provider = canonical_name(settings.LLM_PROVIDER)
    configured = settings.LLM_DEFAULT_MODELS.get(provider, "")
    if configured:
        return configured
    ids = _catalog().ids()
    return ids[0] if ids else ""
