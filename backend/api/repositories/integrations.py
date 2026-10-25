"""Data access for users' own MCP servers (AGENTS.md §7 Repository).

Every lookup is by owner, so another account's integration looks exactly like
one that does not exist. Each write commits its own transaction.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.exceptions import NotFound, ValidationFailed
from api.models import Integration, User


@dataclass(frozen=True)
class StoredHeaders:
    """Header values as persisted: one encrypted JSON object, plus a hint per name."""

    ciphertext: str
    hints: list[dict[str, str]]


@dataclass(frozen=True)
class IntegrationChanges:
    """What a write sets. On an update, ``None`` keeps the stored value."""

    name: str | None = None
    url: str | None = None
    enabled: bool | None = None
    headers: StoredHeaders | None = None
    require_approval: bool | None = None


def _owned_by(user: User) -> Select[tuple[Integration]]:
    return select(Integration).where(Integration.user_id == user.id)


def for_user(session: Session, user: User) -> list[Integration]:
    """The user's integrations, oldest first, so the list keeps its order as it grows."""
    return list(session.scalars(_owned_by(user).order_by(Integration.id)))


def enabled_for(session: Session, user: User) -> list[Integration]:
    query = _owned_by(user).where(Integration.enabled.is_(True)).order_by(Integration.id)
    return list(session.scalars(query))


def get_owned(session: Session, user: User, integration_id: int) -> Integration:
    integration = session.scalar(_owned_by(user).where(Integration.id == integration_id))
    if integration is None:
        raise NotFound(f"Integration {integration_id} was not found.")
    return integration


def name_taken_error(name: str) -> ValidationFailed:
    """The refusal for a name another of the user's integrations already uses."""
    return ValidationFailed(f"You already have an integration named {name}.")


def _commit(session: Session, name: str | None) -> None:
    """Commit. Two requests can pass the name check together, so the database's
    unique name per user has the last word: that is the same refusal, not a 500."""
    try:
        session.commit()
    except IntegrityError as cause:
        session.rollback()
        if name is None:
            raise
        raise name_taken_error(name) from cause


def name_taken(session: Session, user: User, name: str, ignore_id: int | None = None) -> bool:
    """Whether another of the user's integrations already uses ``name``."""
    query = _owned_by(user).where(Integration.name == name)
    if ignore_id is not None:
        query = query.where(Integration.id != ignore_id)
    return session.scalar(query) is not None


def count(session: Session, user: User) -> int:
    query = select(func.count()).select_from(Integration).where(Integration.user_id == user.id)
    return session.scalar(query) or 0


def _apply(integration: Integration, changes: IntegrationChanges) -> None:
    if changes.name is not None:
        integration.name = changes.name
    if changes.url is not None:
        integration.url = changes.url
    if changes.enabled is not None:
        integration.enabled = changes.enabled
    if changes.require_approval is not None:
        integration.require_approval = changes.require_approval
    if changes.headers is not None:
        integration.headers_encrypted = changes.headers.ciphertext
        integration.header_hints = changes.headers.hints


def create(session: Session, user: User, changes: IntegrationChanges) -> Integration:
    """A new integration for ``user``; whatever ``changes`` leaves out starts empty."""
    integration = Integration(
        user_id=user.id,
        name="",
        url="",
        headers_encrypted="",
        header_hints=[],
        enabled=True,
        require_approval=True,
    )
    _apply(integration, changes)
    session.add(integration)
    _commit(session, changes.name)
    return integration


def update(session: Session, integration: Integration, changes: IntegrationChanges) -> Integration:
    _apply(integration, changes)
    _commit(session, changes.name)
    return integration


def delete(session: Session, integration: Integration) -> None:
    session.delete(integration)
    session.commit()
