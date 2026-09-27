"""Provider registry (AGENTS.md §5 O / §7 Factory + Registry).

Adding a provider means adding one entry here, never editing an if/elif chain.
"""

from __future__ import annotations

from collections.abc import Callable

from llm.base import LLMProvider, ProviderConfig
from llm.exceptions import ProviderNotConfigured
from llm.providers import openrouter, together

ProviderFactory = Callable[[ProviderConfig], LLMProvider]

FACTORIES: dict[str, ProviderFactory] = {
    openrouter.NAME: openrouter.build,
    together.NAME: together.build,
}

#: Spellings accepted for each canonical provider name.
ALIASES: dict[str, str] = {
    "open_router": openrouter.NAME,
    "openrouter": openrouter.NAME,
    "together": together.NAME,
    "together_ai": together.NAME,
    "togetherai": together.NAME,
}


def canonical_name(name: str) -> str:
    """Resolve a configured provider name, raising if it is not supported."""
    key = (name or "").strip().lower()
    resolved = ALIASES.get(key, key)
    if resolved not in FACTORIES:
        supported = ", ".join(sorted(FACTORIES))
        raise ProviderNotConfigured(f"Unsupported LLM provider '{name}'. Supported: {supported}.")
    return resolved


def create_provider(name: str, config: ProviderConfig) -> LLMProvider:
    """Build the named provider. Raises ProviderNotConfigured when it cannot."""
    return FACTORIES[canonical_name(name)](config)


def supported_providers() -> list[str]:
    return sorted(FACTORIES)
