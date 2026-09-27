"""Data access for accounts (AGENTS.md §7 Repository)."""

from __future__ import annotations

from sqlalchemy import select
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
