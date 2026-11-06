"""Sending through SMTP: the connection each SMTP_TLS value opens, the message, and
the failures that become ours; without a server, nothing is sent and callers are told."""

from __future__ import annotations

import smtplib
from collections.abc import Callable
from email.message import EmailMessage
from typing import Any

import pytest
from pydantic import ValidationError

from api.exceptions import EmailNotConfigured, EmailNotSent
from api.services.email import (
    CONNECTIONS,
    Email,
    NullSender,
    SmtpSender,
    SmtpSettings,
    email_sender,
)
from config.settings import Settings
from tests.conftest import TEST_SETTINGS

MESSAGE = Email("alice@example.com", "Hi", "Hello\n")


def smtp_settings(tls: str = "starttls", username: str = "robot") -> SmtpSettings:
    return SmtpSettings(
        "mail.example", 587, username, "secret", "AIMIx <no-reply@example.com>", tls, 15.0
    )


class FakeSmtp:
    """Stands in for ``smtplib.SMTP``: records what the sender does with it."""

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.opened = (host, port, timeout)
        self.log: list[str] = []
        self.messages: list[EmailMessage] = []

    def __enter__(self) -> FakeSmtp:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.log.append("quit")

    def starttls(self) -> None:
        self.log.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.log.append(f"login {user}:{password}")

    def send_message(self, message: EmailMessage) -> None:
        self.messages.append(message)


def connecting(opened: list[FakeSmtp]) -> Callable[[str, int, float], Any]:
    def connect(host: str, port: int, timeout: float) -> FakeSmtp:
        fake = FakeSmtp(host, port, timeout)
        opened.append(fake)
        return fake

    return connect


def test_a_message_is_sent_over_starttls_with_the_credentials() -> None:
    opened: list[FakeSmtp] = []

    SmtpSender(smtp_settings(), connecting(opened)).send(MESSAGE)

    (connection,) = opened
    assert connection.opened == ("mail.example", 587, 15.0)
    assert connection.log == ["starttls", "login robot:secret", "quit"]
    (message,) = connection.messages
    assert message["From"] == "AIMIx <no-reply@example.com>"
    assert (message["To"], message["Subject"]) == ("alice@example.com", "Hi")
    assert message.get_content() == "Hello\n"


def test_plain_sends_in_clear_and_without_credentials_nobody_logs_in() -> None:
    opened: list[FakeSmtp] = []

    SmtpSender(smtp_settings("none", username=""), connecting(opened)).send(MESSAGE)

    assert opened[0].log == ["quit"]
    assert set(CONNECTIONS) == {"starttls", "ssl", "none"}
    assert CONNECTIONS["ssl"] is not CONNECTIONS["starttls"]


def test_a_refused_or_unreachable_server_is_our_error() -> None:
    def refusing(host: str, port: int, timeout: float) -> FakeSmtp:
        raise smtplib.SMTPConnectError(421, b"busy")

    def unreachable(host: str, port: int, timeout: float) -> FakeSmtp:
        raise OSError("no route to host")

    with pytest.raises(EmailNotSent) as refused:
        SmtpSender(smtp_settings(), refusing).send(MESSAGE)
    assert "SMTPConnectError" in refused.value.detail
    with pytest.raises(EmailNotSent) as down:
        SmtpSender(smtp_settings(), unreachable).send(MESSAGE)
    assert "OSError" in down.value.detail


def test_without_a_server_nothing_can_be_sent_and_callers_are_told() -> None:
    with pytest.raises(EmailNotConfigured) as refused:
        NullSender().send(MESSAGE)
    assert refused.value.code == "email_not_configured"
    assert isinstance(email_sender(TEST_SETTINGS), NullSender)
    update = {"smtp_host": "mail.example", "smtp_from": "no-reply@example.com"}
    assert isinstance(email_sender(TEST_SETTINGS.model_copy(update=update)), SmtpSender)


def test_a_server_needs_a_sender_address_and_the_public_url_keeps_no_slash() -> None:
    with pytest.raises(ValidationError, match="SMTP_FROM"):
        Settings(_env_file=None, smtp_host="mail.example")  # type: ignore[call-arg]
    settings = Settings(_env_file=None, app_public_url="https://aimix.win/ ")  # type: ignore[call-arg]
    assert settings.app_public_url == "https://aimix.win"
