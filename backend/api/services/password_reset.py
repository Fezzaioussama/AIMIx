"""Resetting a forgotten password by a link sent to the account's email address.

The link carries a signed token of its own type (``TokenSigner``, ``reset``) naming
the account and its token version. Confirming it replaces the password, which
moves the version on: the link works once, and every session of the account ends
with it, as after a password change. Asking never says whether an address has an
account (nothing is answered either way), and one address may ask
PASSWORD_RESET_RATE_LIMIT_REQUESTS times per window. Plain values in and out
(AGENTS.md §2); addresses are never logged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import quote

from sqlalchemy.orm import Session

from api.exceptions import ValidationFailed
from api.repositories import users as repository
from api.security import TokenSigner, hash_password
from api.services import password_policy, rate_limits
from api.services.accounts import normalised_email
from api.services.email import Email, EmailSender
from api.services.rate_limits import RateLimitRequest
from config.settings import Settings

logger = logging.getLogger(__name__)

#: The app's page that takes the token from the link.
RESET_PATH = "/reset-password"
#: The rate-limit action that counts one address's requests.
RESET_REQUESTS = "password-reset"
TOO_MANY_REQUESTS = "Too many reset requests for this address. Try again later."
TOKEN_INVALID = "This link is not valid any more. Ask for a new one."


@dataclass(frozen=True)
class ResetPolicy:
    """Where a link points, how often one address may ask, and the hash work factor."""

    public_url: str
    rate_limit: int
    window_seconds: int
    #: Keys the rate-limit counters, so the table holds no address.
    secret_key: str
    hash_iterations: int

    def requests_of(self, address: str) -> RateLimitRequest:
        return RateLimitRequest(
            f"reset:{address}",
            RESET_REQUESTS,
            self.rate_limit,
            self.window_seconds,
            TOO_MANY_REQUESTS,
        )


def reset_policy(settings: Settings) -> ResetPolicy:
    return ResetPolicy(
        settings.app_public_url,
        settings.password_reset_rate_limit_requests,
        settings.password_reset_rate_limit_window_seconds,
        settings.secret_key,
        settings.password_hash_iterations,
    )


@dataclass(frozen=True)
class ResetFlow:
    """What a reset needs: storage, the signer of the links, the sender, the policy."""

    session: Session
    signer: TokenSigner
    sender: EmailSender
    policy: ResetPolicy


@dataclass(frozen=True)
class ResetConfirmation:
    token: str
    password: str


def reset_link(public_url: str, token: str) -> str:
    return f"{public_url}{RESET_PATH}?token={quote(token, safe='')}"


def reset_email(to: str, username: str, link: str, minutes: float) -> Email:
    """Pure: the message a reset request sends."""
    text = (
        f"Hello {username},\n\n"
        "Someone asked to reset the password of your AIMIx account. Open this link "
        f"within {minutes:g} minutes to choose a new one:\n\n{link}\n\n"
        "If it was not you, ignore this email: your password stays as it is.\n"
    )
    return Email(to, "Reset your AIMIx password", text)


def request_reset(flow: ResetFlow, address: str) -> None:
    """Email a reset link to the account using ``address``, if any. Nothing says
    whether one does; a ``Throttled`` past the address's allowance, and the
    sender's own error when the server cannot send, do."""
    address = normalised_email(address)
    rate_limits.enforce(flow.session, flow.policy.secret_key, flow.policy.requests_of(address))
    user = repository.get_by_email(flow.session, address)
    if user is None:
        return
    token = flow.signer.issue(user.id, "reset", user.token_version)
    minutes = flow.signer.reset_lifetime.total_seconds() / 60
    link = reset_link(flow.policy.public_url, token)
    flow.sender.send(reset_email(address, user.username, link, minutes))
    logger.info("accounts.reset_requested user_id=%s", user.id)


def confirm_reset(flow: ResetFlow, confirmation: ResetConfirmation) -> None:
    """Replace the password of the account the token names, once, if the token is
    still valid and the password follows the rules; every session of the
    account ends."""
    subject = flow.signer.subject(confirmation.token, "reset")
    user = repository.get(flow.session, subject.user_id) if subject is not None else None
    if subject is None or user is None or subject.version != user.token_version:
        raise ValidationFailed(f"token: {TOKEN_INVALID}")
    problems = password_policy.problems(confirmation.password, user.username)
    if problems:
        raise ValidationFailed(f"password: {' '.join(problems)}")
    new_hash = hash_password(confirmation.password, flow.policy.hash_iterations)
    repository.replace_password(flow.session, user, new_hash)
    logger.info("accounts.password_reset user_id=%s", user.id)
