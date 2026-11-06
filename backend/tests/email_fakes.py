"""Senders shared by the email tests: one that keeps what it is given, one that fails."""

from __future__ import annotations

from api.exceptions import EmailNotSent
from api.services.email import Email


class Outbox:
    """An ``EmailSender`` that keeps every message instead of sending it."""

    def __init__(self) -> None:
        self.sent: list[Email] = []

    def send(self, email: Email) -> None:
        self.sent.append(email)


class Refusing:
    """An ``EmailSender`` whose server refuses every message."""

    def send(self, email: Email) -> None:
        raise EmailNotSent("The email server did not take the message (SMTPException).")
