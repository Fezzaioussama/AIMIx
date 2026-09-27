"""Translates provider-layer failures into domain errors (AGENTS.md §5 L).

Every service that calls a provider routes its exceptions through here, so one
mapping serves them all rather than a try/except per call site (§3).
"""

from __future__ import annotations

from api import exceptions as domain
from llm import exceptions as llm_exceptions

#: Provider exception -> domain exception. A new provider failure mode is one
#: entry here, not a new branch in each service (§5 O).
PROVIDER_ERROR_MAP: list[tuple[type[llm_exceptions.LLMError], type[domain.DomainError]]] = [
    (llm_exceptions.ProviderNotConfigured, domain.ProviderNotConfigured),
    (llm_exceptions.ProviderTimeout, domain.ProviderTimedOut),
    (llm_exceptions.ProviderRequestError, domain.ProviderUnavailable),
]


def as_domain_error(cause: llm_exceptions.LLMError) -> domain.DomainError:
    for provider_error, domain_error in PROVIDER_ERROR_MAP:
        if isinstance(cause, provider_error):
            return domain_error(str(cause))
    return domain.ProviderUnavailable(str(cause))
