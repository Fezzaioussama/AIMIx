"""Accounts: registration, sign-in and token exchange.

Takes and returns plain values; hashing and signing come from api.security and
storage from the users repository, so each piece has one reason to change (§5 S).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from api.exceptions import NotAuthenticated, ValidationFailed
from api.models import User
from api.repositories import users as repository
from api.security import TokenSigner, hash_password, verify_password
from api.services import password_policy

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = "No active account found with the given credentials."
INVALID_TOKEN = "Given token not valid for any token type."


@dataclass(frozen=True)
class TokenPair:
    access: str
    refresh: str


def register(session: Session, username: str, password: str, iterations: int) -> User:
    """Create an account, or raise ValidationFailed listing what is wrong."""
    if repository.get_by_username(session, username) is not None:
        raise ValidationFailed("username: A user with that username already exists.")
    problems = password_policy.problems(password, username)
    if problems:
        raise ValidationFailed(f"password: {' '.join(problems)}")
    user = repository.create(session, username, hash_password(password, iterations))
    logger.info("accounts.registered user_id=%s", user.id)
    return user


def sign_in(session: Session, signer: TokenSigner, username: str, password: str) -> TokenPair:
    user = repository.get_by_username(session, username)
    if user is None or not verify_password(password, user.password_hash):
        raise NotAuthenticated(INVALID_CREDENTIALS)
    return TokenPair(
        access=signer.issue(user.id, "access"), refresh=signer.issue(user.id, "refresh")
    )


def refresh_access(session: Session, signer: TokenSigner, refresh_token: str) -> str:
    """A new access token for a still-valid refresh token (no rotation)."""
    user = _user_for(session, signer.user_id(refresh_token, "refresh"))
    return signer.issue(user.id, "access")


def authenticate(session: Session, signer: TokenSigner, access_token: str) -> User:
    """The account an access token belongs to, or NotAuthenticated."""
    return _user_for(session, signer.user_id(access_token, "access"))


def _user_for(session: Session, user_id: int | None) -> User:
    user = repository.get(session, user_id) if user_id is not None else None
    if user is None:
        raise NotAuthenticated(INVALID_TOKEN)
    return user
