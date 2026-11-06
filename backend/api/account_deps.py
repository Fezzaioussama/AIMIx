"""The accounts' part of ``deps.py``: the mail sender and the password-reset flow.
Tests swap the sender through ``app.dependency_overrides`` like any other dependency."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from api.deps import AppSettings, DbSession, Signer
from api.services.email import EmailSender, email_sender
from api.services.password_reset import ResetFlow, reset_policy


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
