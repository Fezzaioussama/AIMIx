"""Which model ids each provider offers, and which one is its default.

Derived from the provider catalogues, so the list the API validates against,
the list it serves to clients, and the list the provider can actually reach
are one and the same (AGENTS.md §3). A provider argument left out means the
deployment-wide LLM_PROVIDER; per-user choices come from api.services.llm_settings.
"""

from __future__ import annotations

from config.settings import get_settings
from llm.catalog import CATALOGS
from llm.registry import canonical_name, supported_providers


def provider_names() -> list[str]:
    return supported_providers()


def resolve_provider(name: str | None = None) -> str:
    """The canonical provider: ``name``, else LLM_PROVIDER. Raises if unsupported."""
    return canonical_name(name or get_settings().llm_provider)


def known_model_ids() -> list[str]:
    """Every catalogued model id, across providers."""
    ids = (model_id for catalog in CATALOGS.values() for model_id in catalog.ids())
    return list(dict.fromkeys(ids))


def available_model_ids(provider: str | None = None, default: str = "") -> list[str]:
    """Model ids the provider exposes, its default first."""
    name = resolve_provider(provider)
    ids = CATALOGS[name].ids()
    chosen = default or default_model_id(name)
    if chosen in ids:
        return [chosen, *(model_id for model_id in ids if model_id != chosen)]
    return ids


def default_model_id(provider: str | None = None, preferred: str = "") -> str:
    """``preferred`` when the provider offers it, else the configured default."""
    name = resolve_provider(provider)
    ids = CATALOGS[name].ids()
    if preferred in ids:
        return preferred
    configured = get_settings().llm_default_models.get(name, "")
    if configured:
        return configured
    return ids[0] if ids else ""
