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
from api.security import (
    TokenSigner,
    hash_iterations,
    hash_password,
    verify_nothing,
    verify_password,
)
from api.services import password_policy, rate_limits
from api.services.rate_limits import RateLimitRequest
from config.settings import Settings

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = "No active account found with the given credentials."
INVALID_TOKEN = "Given token not valid for any token type."
ACCOUNT_THROTTLED = "Too many failed sign-ins for this account. Try again later."
#: The rate-limit action that counts one username's failed sign-ins.
FAILED_SIGN_INS = "sign-in-failures"


@dataclass(frozen=True)
class TokenPair:
    access: str
    refresh: str


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str


@dataclass(frozen=True)
class SignInPolicy:
    """What a sign-in costs and how many failures one username may take."""

    hash_iterations: int
    failure_limit: int
    failure_window_seconds: int
    #: Keys the failure counters, so the table holds no username.
    secret_key: str

    def failures(self, username: str) -> RateLimitRequest:
        # Lower-cased, so "Alice" and "alice" share one counter.
        return RateLimitRequest(
            f"account:{username.lower()}",
            FAILED_SIGN_INS,
            self.failure_limit,
            self.failure_window_seconds,
            ACCOUNT_THROTTLED,
        )


def sign_in_policy(settings: Settings) -> SignInPolicy:
    return SignInPolicy(
        settings.password_hash_iterations,
        settings.auth_account_failure_limit,
        settings.auth_account_failure_window_seconds,
        settings.secret_key,
    )


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


def sign_in(
    session: Session, signer: TokenSigner, credentials: Credentials, policy: SignInPolicy
) -> TokenPair:
    """Tokens for valid credentials. A username past its failure limit is refused
    before its password is checked; an unknown one costs the same as a known one."""
    failures = policy.failures(credentials.username)
    rate_limits.ensure_room(session, policy.secret_key, failures)
    user = _verified(session, credentials, policy.hash_iterations)
    if user is None:
        rate_limits.count(session, policy.secret_key, failures)
        raise NotAuthenticated(INVALID_CREDENTIALS)
    rate_limits.reset(session, policy.secret_key, failures)
    if hash_iterations(user.password_hash) != policy.hash_iterations:
        # An imported or older hash moves to the configured work factor.
        repository.set_password_hash(
            session, user, hash_password(credentials.password, policy.hash_iterations)
        )
    tokens = _issue(signer, user)
    repository.set_refresh_token(session, user, _token_hash(tokens.refresh))
    return tokens


def _verified(session: Session, credentials: Credentials, iterations: int) -> User | None:
    user = repository.get_by_username(session, credentials.username)
    if user is None:
        verify_nothing(credentials.password, iterations)
        return None
    return user if verify_password(credentials.password, user.password_hash) else None


def refresh_access(session: Session, signer: TokenSigner, refresh_token: str) -> TokenPair:
    """Rotate a valid refresh token and issue a new access token."""
    user = _user_for(session, signer.user_id(refresh_token, "refresh"))
    tokens = _issue(signer, user)
    replaced = repository.replace_refresh_token(
        session, user.id, _token_hash(refresh_token), _token_hash(tokens.refresh)
    )
    if not replaced:
        raise NotAuthenticated(INVALID_TOKEN)
    return tokens


def revoke_refresh(session: Session, signer: TokenSigner, refresh_token: str) -> None:
    """Invalidate the presented refresh token and every access token issued to
    its account; invalid input is an idempotent no-op."""
    user_id = signer.user_id(refresh_token, "refresh")
    if user_id is None:
        return
    if repository.end_session(session, user_id, _token_hash(refresh_token)):
        logger.info("accounts.signed_out user_id=%s", user_id)


def _issue(signer: TokenSigner, user: User) -> TokenPair:
    return TokenPair(
        access=signer.issue(user.id, "access", user.token_version),
        refresh=signer.issue(user.id, "refresh"),
    )


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def authenticate(session: Session, signer: TokenSigner, access_token: str) -> User:
    """The account an access token belongs to, or NotAuthenticated. A token
    issued before the account last signed out is refused."""
    subject = signer.subject(access_token, "access")
    user = _user_for(session, subject.user_id if subject is not None else None)
    if subject is None or subject.version != user.token_version:
        raise NotAuthenticated(INVALID_TOKEN)
    return user


def _user_for(session: Session, user_id: int | None) -> User:
    user = repository.get(session, user_id) if user_id is not None else None
    if user is None:
        raise NotAuthenticated(INVALID_TOKEN)
    return user
