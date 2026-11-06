"""The accounts' part of ``deps.py``: the mail sender, the password-reset flow and
the account's usage view. Tests swap these through ``app.dependency_overrides`` like
any other dependency."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from api.deps import AppSettings, CurrentUser, DbSession, Profile, Signer
from api.models import User
from api.services.account_usage import daily_allowance
from api.services.email import EmailSender, email_sender
from api.services.password_reset import ResetFlow, reset_policy
from api.services.run_budget import NO_BUDGET, RunBudget


def mail_sender(settings: AppSettings) -> EmailSender:
    """Where the app's emails go out: SMTP_HOST, or a sender that refuses."""
    return email_sender(settings)


Mailer = Annotated[EmailSender, Depends(mail_sender)]


def password_reset_flow(
    session: DbSession, signer: Signer, sender: Mailer, settings: AppSettings
) -> ResetFlow:
    """A password reset by link: the signer of the links, the sender, the policy."""
    return ResetFlow(session, signer, sender, reset_policy(settings))


PasswordResets = Annotated[ResetFlow, Depends(password_reset_flow)]


@dataclass(frozen=True)
class UsageAccess:
    """The signed-in account's usage: its storage, and the day's allowance of the
    server's key that applies to it (none with a key of its own)."""

    session: Session
    user: User
    allowance: RunBudget


def usage_access(
    session: DbSession, user: CurrentUser, profile: Profile, settings: AppSettings
) -> UsageAccess:
    allowance = NO_BUDGET if profile.api_key else daily_allowance(settings)
    return UsageAccess(session, user, allowance)


UsageView = Annotated[UsageAccess, Depends(usage_access)]
