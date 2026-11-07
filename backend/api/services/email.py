"""Sending email: one plain-text message at a time, with files attached when there are
any, through the operator's SMTP server, or nowhere when none is configured.

``SmtpSender`` is the adapter around the standard library's ``smtplib`` (§7 Adapter),
the one place its failures become ours; nothing else in the app imports it. Every
send is bounded by SMTP_TIMEOUT_SECONDS and never retried. Plain values in and out
(AGENTS.md §2); addresses are never logged.
"""

from __future__ import annotations

import smtplib
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from api.exceptions import EmailNotConfigured, EmailNotSent
from config.settings import Settings


@dataclass(frozen=True)
class Attachment:
    """One file sent with a message (§7 Value Object)."""

    filename: str
    content: bytes
    media_type: str


@dataclass(frozen=True)
class Email:
    """One plain-text message, with files attached when there are any (§7 Value Object)."""

    to: str
    subject: str
    text: str
    attachments: tuple[Attachment, ...] = ()


class EmailSender(Protocol):
    """Port: deliver one message, or raise ``EmailNotSent``."""

    def send(self, email: Email) -> None: ...


#: Opens a connection: host, port, timeout in seconds.
SmtpFactory = Callable[[str, int, float], smtplib.SMTP]


def _plain(host: str, port: int, timeout: float) -> smtplib.SMTP:
    return smtplib.SMTP(host, port, timeout=timeout)


def _ssl(host: str, port: int, timeout: float) -> smtplib.SMTP:
    return smtplib.SMTP_SSL(host, port, timeout=timeout)


#: How each SMTP_TLS value opens the connection (Strategy + Registry); starttls
#: upgrades a plain one once it is open.
CONNECTIONS: dict[str, SmtpFactory] = {"starttls": _plain, "none": _plain, "ssl": _ssl}


@dataclass(frozen=True)
class SmtpSettings:
    """The SMTP_* settings (§7 Value Object)."""

    host: str
    port: int
    username: str
    password: str
    sender: str
    tls: str
    timeout_seconds: float


def smtp_settings(settings: Settings) -> SmtpSettings:
    return SmtpSettings(
        settings.smtp_host,
        settings.smtp_port,
        settings.smtp_username,
        settings.smtp_password,
        settings.smtp_from,
        settings.smtp_tls,
        settings.smtp_timeout_seconds,
    )


class SmtpSender:
    """Sends through an SMTP server: one connection per message, within the timeout."""

    def __init__(self, settings: SmtpSettings, connect: SmtpFactory | None = None) -> None:
        self._settings = settings
        #: Tests pass a fake; the app opens the real connection its SMTP_TLS names.
        self._connect = connect or CONNECTIONS[settings.tls]

    def send(self, email: Email) -> None:
        message = EmailMessage()
        message["From"] = self._settings.sender
        message["To"] = email.to
        message["Subject"] = email.subject
        message.set_content(email.text)
        for attachment in email.attachments:
            maintype, _, subtype = attachment.media_type.partition("/")
            message.add_attachment(
                attachment.content,
                maintype=maintype or "application",
                subtype=subtype or "octet-stream",
                filename=attachment.filename,
            )
        try:
            with self._connect(
                self._settings.host, self._settings.port, self._settings.timeout_seconds
            ) as connection:
                if self._settings.tls == "starttls":
                    connection.starttls()
                if self._settings.username:
                    connection.login(self._settings.username, self._settings.password)
                connection.send_message(message)
        except (OSError, smtplib.SMTPException) as cause:
            # The adapter's boundary: a refused or unreachable server becomes our error.
            raise EmailNotSent(
                f"The email server did not take the message ({type(cause).__name__})."
            ) from cause


class NullSender:
    """Stands in while SMTP_HOST is empty (Null Object): nothing is sent, and a
    caller that must send is told why."""

    def send(self, email: Email) -> None:
        raise EmailNotConfigured("This server cannot send email: SMTP_HOST is not set.")


def email_sender(settings: Settings) -> EmailSender:
    """The app's sender: SMTP when configured, else one that refuses."""
    if not settings.smtp_host:
        return NullSender()
    return SmtpSender(smtp_settings(settings))
