"""Accounts: registration, sign-in and token exchange.

Takes and returns plain values; hashing and signing come from api.security and
storage from the users repository, so each piece has one reason to change (§5 S).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from api.exceptions import NotAuthenticated, PermissionDenied, ValidationFailed
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


def ensure_registration_allowed(enabled: bool) -> None:
    if not enabled:
        raise PermissionDenied("Public account registration is disabled.")


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
    tokens = TokenPair(
        access=signer.issue(user.id, "access"), refresh=signer.issue(user.id, "refresh")
    )
    repository.set_refresh_token(session, user, _token_hash(tokens.refresh))
    return tokens


def refresh_access(session: Session, signer: TokenSigner, refresh_token: str) -> TokenPair:
    """Rotate a valid refresh token and issue a new access token."""
    user = _user_for(session, signer.user_id(refresh_token, "refresh"))
    tokens = TokenPair(
        access=signer.issue(user.id, "access"), refresh=signer.issue(user.id, "refresh")
    )
    replaced = repository.replace_refresh_token(
        session, user.id, _token_hash(refresh_token), _token_hash(tokens.refresh)
    )
    if not replaced:
        raise NotAuthenticated(INVALID_TOKEN)
    return tokens


def revoke_refresh(session: Session, signer: TokenSigner, refresh_token: str) -> None:
    """Invalidate the presented refresh token; invalid input is an idempotent no-op."""
    user_id = signer.user_id(refresh_token, "refresh")
    if user_id is not None:
        repository.replace_refresh_token(session, user_id, _token_hash(refresh_token), "")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def authenticate(session: Session, signer: TokenSigner, access_token: str) -> User:
    """The account an access token belongs to, or NotAuthenticated."""
    return _user_for(session, signer.user_id(access_token, "access"))


def _user_for(session: Session, user_id: int | None) -> User:
    user = repository.get(session, user_id) if user_id is not None else None
    if user is None:
        raise NotAuthenticated(INVALID_TOKEN)
    return user
