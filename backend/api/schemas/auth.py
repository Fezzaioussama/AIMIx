"""Contracts for registration, sign-in, token refresh and password resets."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from api.models import EMAIL_MAX_LENGTH, USERNAME_MAX_LENGTH

PASSWORD_MAX_LENGTH = 1_024
#: One @ with something on both sides and a dot after it; the mail server judges the rest.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
#: Trimmed first, so a pasted address with a space around it is taken; the service lower-cases it.
EmailAddress = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=3, max_length=EMAIL_MAX_LENGTH, pattern=EMAIL_PATTERN
    ),
]
#: A reset link's token: a JWT, far shorter than this.
RESET_TOKEN_MAX_LENGTH = 2_048


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=USERNAME_MAX_LENGTH, pattern=r"^[\w.@+-]+$")
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)
    #: Optional: where reset links and notifications go.
    email: EmailAddress | None = None


class RegisterResponse(BaseModel):
    username: str


class LoginRequest(BaseModel):
    #: The username, or the account's email address.
    username: str = Field(min_length=1, max_length=max(USERNAME_MAX_LENGTH, EMAIL_MAX_LENGTH))
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class AccessTokenResponse(BaseModel):
    access: str


class WhoAmIResponse(BaseModel):
    message: str
    user_id: int
    username: str


class PasswordResetRequest(BaseModel):
    email: EmailAddress


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=1, max_length=RESET_TOKEN_MAX_LENGTH)
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)
