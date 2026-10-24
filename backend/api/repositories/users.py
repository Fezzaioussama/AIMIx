"""Data access for accounts (AGENTS.md §7 Repository)."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from api.models import User


def get(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def get_by_username(session: Session, username: str) -> User | None:
    return session.scalar(select(User).where(User.username == username))


def create(session: Session, username: str, password_hash: str) -> User:
    user = User(username=username, password_hash=password_hash)
    session.add(user)
    session.commit()
    return user


def set_refresh_token(session: Session, user: User, token_hash: str) -> None:
    user.refresh_token_hash = token_hash
    session.commit()


def replace_refresh_token(
    session: Session, user_id: int, current_hash: str, replacement_hash: str
) -> bool:
    """Atomically rotate or revoke a token, rejecting concurrent replay."""
    statement = (
        update(User)
        .where(User.id == user_id, User.refresh_token_hash == current_hash)
        .values(refresh_token_hash=replacement_hash)
    )
    replaced = session.execute(statement).rowcount == 1
    session.commit()
    return replaced
