"""Data access for accounts (AGENTS.md §7 Repository)."""

from __future__ import annotations

import secrets
from typing import Any, cast

from sqlalchemy import delete as delete_statement
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from api.models import User

#: New accounts draw their first token version below this: odds of about one in a
#: billion that a deleted account's token matches, and room for 2**30 sign-outs
#: in a 32-bit column.
FIRST_TOKEN_VERSIONS = 2**30


def get(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def get_by_username(session: Session, username: str) -> User | None:
    return session.scalar(select(User).where(User.username == username))


def create(session: Session, username: str, password_hash: str) -> User:
    """A new account, at a random token version. SQLite gives a deleted account's id
    to the next one, and an access token names an id and a version: starting from 0,
    the deleted account's tokens would sign in as the new one."""
    version = secrets.randbelow(FIRST_TOKEN_VERSIONS)
    user = User(username=username, password_hash=password_hash, token_version=version)
    session.add(user)
    session.commit()
    return user


def set_refresh_token(session: Session, user: User, token_hash: str) -> None:
    user.refresh_token_hash = token_hash
    session.commit()


def set_password_hash(session: Session, user: User, password_hash: str) -> None:
    user.password_hash = password_hash
    session.commit()


def replace_password(session: Session, user: User, password_hash: str) -> None:
    """Store a new password and end every session: the refresh token is dropped,
    and the access tokens issued so far carry an older version."""
    user.password_hash = password_hash
    user.refresh_token_hash = ""
    user.token_version += 1
    session.commit()


def delete(session: Session, user: User) -> None:
    """Delete the account in one statement: the database deletes every row it owns
    with it (ON DELETE CASCADE), so none of them is loaded first."""
    session.execute(delete_statement(User).where(User.id == user.id))
    session.commit()


def replace_refresh_token(
    session: Session, user_id: int, current_hash: str, replacement_hash: str
) -> bool:
    """Atomically rotate a token, rejecting concurrent replay."""
    return _swap_refresh_token(
        session, user_id, current_hash, {"refresh_token_hash": replacement_hash}
    )


def end_session(session: Session, user_id: int, current_hash: str) -> bool:
    """Atomically revoke the refresh token and, by moving the account's token
    version on, every access token issued before."""
    values = {"refresh_token_hash": "", "token_version": User.token_version + 1}
    return _swap_refresh_token(session, user_id, current_hash, values)


def _swap_refresh_token(
    session: Session, user_id: int, current_hash: str, values: dict[str, Any]
) -> bool:
    """Apply ``values`` only while ``current_hash`` is the account's refresh token."""
    statement = (
        update(User)
        .where(User.id == user_id, User.refresh_token_hash == current_hash)
        .values(values)
    )
    result = cast("CursorResult[Any]", session.execute(statement))
    replaced = result.rowcount == 1
    session.commit()
    return replaced
