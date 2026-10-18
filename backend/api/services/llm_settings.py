"""Each user's LLM provider, API keys and default models (the Settings page).

What a user saved wins; anything they did not save falls back to backend/.env,
so a deployment configured only through the environment keeps working. Keys
are encrypted at rest and never returned — only their last characters.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from api.exceptions import ProviderNotConfigured
from api.models import API_KEY_HINT_LENGTH, ProviderSetting, User
from api.repositories import provider_settings as repository
from api.repositories.provider_settings import ProviderValues, StoredKey
from api.security import SecretBox, UnreadableSecret
from api.services.catalog import (
    available_model_ids,
    default_model_id,
    provider_names,
    resolve_provider,
)
from api.services.errors import as_domain_error
from api.services.llm import LLMProfile, has_environment_key
from llm import exceptions as llm_exceptions

logger = logging.getLogger(__name__)

KeySource = Literal["saved", "environment", "none"]


@dataclass(frozen=True)
class ProviderView:
    """One provider as the Settings page shows it. Never carries the key itself."""

    name: str
    key_source: KeySource
    key_hint: str
    default_model: str
    models: list[str]


@dataclass(frozen=True)
class SettingsView:
    provider: str
    providers: list[ProviderView]


@dataclass(frozen=True)
class ProviderChoice:
    """A provider's new settings; ``api_key`` None keeps the saved key."""

    name: str
    default_model: str
    api_key: str | None = None


@dataclass(frozen=True)
class SettingsUpdate:
    provider: str
    providers: list[ProviderChoice]


def _active_provider(user: User) -> str:
    try:
        return resolve_provider(user.llm_provider)
    except llm_exceptions.LLMError as cause:
        raise as_domain_error(cause) from cause


def _saved_model(saved: ProviderSetting | None) -> str:
    return saved.default_model if saved else ""


def _reveal(box: SecretBox, saved: ProviderSetting | None) -> str:
    if saved is None or not saved.api_key_encrypted:
        return ""
    try:
        return box.open(saved.api_key_encrypted)
    except UnreadableSecret as cause:
        raise ProviderNotConfigured(
            f"Your saved {saved.provider} API key can no longer be read because the "
            "server's SECRET_KEY changed. Enter it again on the Settings page."
        ) from cause


def environment_profile() -> LLMProfile:
    """The deployment-wide profile, for callers without a user (the CLI)."""
    provider = resolve_provider()
    return LLMProfile(provider, default_model_id(provider))


def resolve_profile(session: Session, user: User, box: SecretBox) -> LLMProfile:
    """The provider, default model and key this user's requests use.

    The key is decrypted here, once per request, and lives only in the returned
    profile; it is never written back or cached in clear.
    """
    provider = _active_provider(user)
    saved = repository.get(session, user, provider)
    return LLMProfile(
        provider=provider,
        default_model=default_model_id(provider, _saved_model(saved)),
        api_key=_reveal(box, saved),
    )


def _key_source(name: str, saved: ProviderSetting | None) -> KeySource:
    if saved is not None and saved.api_key_encrypted:
        return "saved"
    return "environment" if has_environment_key(name) else "none"


def _view(name: str, saved: ProviderSetting | None) -> ProviderView:
    default = default_model_id(name, _saved_model(saved))
    return ProviderView(
        name=name,
        key_source=_key_source(name, saved),
        key_hint=saved.api_key_hint if saved else "",
        default_model=default,
        models=available_model_ids(name, default),
    )


def read(session: Session, user: User) -> SettingsView:
    rows = repository.for_user(session, user)
    return SettingsView(
        provider=_active_provider(user),
        providers=[_view(name, rows.get(name)) for name in provider_names()],
    )


def _stored(box: SecretBox, api_key: str | None) -> StoredKey | None:
    if api_key is None:
        return None
    return StoredKey(ciphertext=box.seal(api_key), hint=api_key[-API_KEY_HINT_LENGTH:])


def save(session: Session, user: User, box: SecretBox, update: SettingsUpdate) -> SettingsView:
    """Apply the Settings form. Saving the same form twice changes nothing."""
    values = [
        ProviderValues(choice.name, choice.default_model, _stored(box, choice.api_key))
        for choice in update.providers
    ]
    repository.save(session, user, update.provider, values)
    # Counts only: neither the key nor its hint reaches the logs (§6).
    logger.info(
        "llm_settings.saved user_id=%s provider=%s keys_replaced=%d",
        user.id,
        update.provider,
        sum(value.key is not None for value in values),
    )
    return read(session, user)


def remove_key(session: Session, user: User, provider: str) -> SettingsView:
    repository.clear_key(session, user, provider)
    logger.info("llm_settings.key_removed user_id=%s provider=%s", user.id, provider)
    return read(session, user)
