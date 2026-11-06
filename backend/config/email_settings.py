"""Settings of outgoing email: the address of the app that links in emails point at,
the SMTP server the app sends through, password-reset links and notifications."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from config.fields import Secret


class EmailSettings(BaseModel):
    # The app as people open it in a browser, for the links emails carry (a
    # password-reset link, a run's page). Stored without a trailing slash.
    app_public_url: str = Field("http://localhost:4200", validation_alias="APP_PUBLIC_URL")
    # --- Outgoing email (api/services/email.py) ---------------------------------
    # The SMTP server; empty sends no email at all: a password reset is refused
    # (503 email_not_configured) and notifications are skipped.
    smtp_host: str = Field("", validation_alias="SMTP_HOST")
    smtp_port: int = Field(587, ge=1, le=65535, validation_alias="SMTP_PORT")
    smtp_username: str = Field("", validation_alias="SMTP_USERNAME")
    smtp_password: Secret = Field("", validation_alias="SMTP_PASSWORD")
    # The From address ("AIMIx <no-reply@example.com>"); required with a host.
    smtp_from: str = Field("", validation_alias="SMTP_FROM")
    # starttls upgrades the connection before sending (port 587), ssl opens it
    # encrypted (port 465), none sends in clear (a relay on a private network).
    smtp_tls: Literal["starttls", "ssl", "none"] = Field("starttls", validation_alias="SMTP_TLS")
    smtp_timeout_seconds: float = Field(15.0, gt=0, validation_alias="SMTP_TIMEOUT_SECONDS")
    # --- Password reset (POST /password-reset) ----------------------------------
    # How long a reset link works, and how often one address may ask for one.
    password_reset_minutes: float = Field(30.0, gt=0, validation_alias="PASSWORD_RESET_MINUTES")
    password_reset_rate_limit_requests: int = Field(
        5, ge=1, validation_alias="PASSWORD_RESET_RATE_LIMIT_REQUESTS"
    )
    password_reset_rate_limit_window_seconds: int = Field(
        3600, ge=1, validation_alias="PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS"
    )
    # --- Notifications (api/services/notifications.py) --------------------------
    # How much of a run's result the email about its end carries (characters).
    notification_result_max_chars: int = Field(
        4000, ge=0, validation_alias="NOTIFICATION_RESULT_MAX_CHARS"
    )

    @field_validator("app_public_url", mode="after")
    @classmethod
    def _without_trailing_slash(cls, value: str) -> str:
        return value.strip().rstrip("/")

    @model_validator(mode="after")
    def _sender_with_host(self) -> EmailSettings:
        """Fail fast (§6): a server to send through needs an address to send from."""
        if self.smtp_host and not self.smtp_from:
            raise ValueError("SMTP_FROM must be set with SMTP_HOST.")
        return self
