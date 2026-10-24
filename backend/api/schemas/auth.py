"""Contracts for registration, sign-in and token refresh."""

from __future__ import annotations

from pydantic import BaseModel, Field

from api.models import USERNAME_MAX_LENGTH

PASSWORD_MAX_LENGTH = 1_024
class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=USERNAME_MAX_LENGTH, pattern=r"^[\w.@+-]+$")
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class RegisterResponse(BaseModel):
    username: str


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=USERNAME_MAX_LENGTH)
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class AccessTokenResponse(BaseModel):
    access: str


class WhoAmIResponse(BaseModel):
    message: str
    user_id: int
