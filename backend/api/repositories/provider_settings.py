"""Data access for users' LLM provider settings (AGENTS.md §7 Repository).

Every lookup is by owner, so one account's keys are never reachable through
another's. Each write commits its own transaction.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from api.models import ProviderSetting, User


@dataclass(frozen=True)
class StoredKey:
    """An API key as it is persisted: encrypted, plus its last characters."""

    ciphertext: str
    hint: str


@dataclass(frozen=True)
class ProviderValues:
    """What one save writes for one provider; ``key`` None keeps the stored key."""

    provider: str
    default_model: str
    key: StoredKey | None = None


def _owned_by(user: User) -> Select[tuple[ProviderSetting]]:
    return select(ProviderSetting).where(ProviderSetting.user_id == user.id)


def for_user(session: Session, user: User) -> dict[str, ProviderSetting]:
    """The user's saved settings, keyed by provider name."""
    return {row.provider: row for row in session.scalars(_owned_by(user))}


def get(session: Session, user: User, provider: str) -> ProviderSetting | None:
    return session.scalar(_owned_by(user).where(ProviderSetting.provider == provider))


def save(
    session: Session, user: User, active_provider: str, values: Iterable[ProviderValues]
) -> None:
    """Choose the active provider and upsert each provider's row, in one transaction."""
    user.llm_provider = active_provider
    # One query for the user's rows, then insert-or-update each provider in memory.
    rows = for_user(session, user)
    for value in values:
        row = rows.get(value.provider)
        if row is None:
            row = ProviderSetting(user=user, provider=value.provider)
            session.add(row)
        row.default_model = value.default_model
        if value.key is not None:
            row.api_key_encrypted = value.key.ciphertext
            row.api_key_hint = value.key.hint
    session.commit()


def clear_key(session: Session, user: User, provider: str) -> None:
    """Forget the saved key; a no-op when none is saved (idempotent)."""
    row = get(session, user, provider)
    if row is not None and row.api_key_encrypted:
        row.api_key_encrypted = ""
        row.api_key_hint = ""
        session.commit()
