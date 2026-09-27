"""Exceptions every provider must raise, so callers can treat them alike.

AGENTS.md §5 L: an implementation that signals failure differently from its
siblings breaks callers. Providers normalise SDK-specific errors into these.
"""

from __future__ import annotations


class LLMError(Exception):
    """Base class for every failure originating in the provider layer."""


class ProviderNotConfigured(LLMError):
    """The provider cannot be built — missing key, unknown name, bad settings."""


class ProviderTimeout(LLMError):
    """The provider did not answer within the configured timeout."""


class ProviderRequestError(LLMError):
    """The provider rejected the request or returned an unusable response."""
