"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from api.deps import AppSettings, CurrentUser, DbSession, Signer
from api.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenPairResponse,
    WhoAmIResponse,
)
from api.services import accounts

#: Public on purpose: this is how an account comes into existence and signs in (§6).
public_router = APIRouter(tags=["auth"])
router = APIRouter(tags=["auth"])


@public_router.post("/register", status_code=201)
def register(body: RegisterRequest, session: DbSession, settings: AppSettings) -> RegisterResponse:
    user = accounts.register(
        session, body.username, body.password, settings.password_hash_iterations
    )
    return RegisterResponse(username=user.username)


@public_router.post("/login")
def login(body: LoginRequest, session: DbSession, signer: Signer) -> TokenPairResponse:
    tokens = accounts.sign_in(session, signer, body.username, body.password)
    return TokenPairResponse(access=tokens.access, refresh=tokens.refresh)


@public_router.post("/token/refresh")
def refresh(body: RefreshRequest, session: DbSession, signer: Signer) -> AccessTokenResponse:
    return AccessTokenResponse(access=accounts.refresh_access(session, signer, body.refresh))


@router.get("/protected")
def protected(user: CurrentUser) -> WhoAmIResponse:
    """Cheap way for the client to confirm a token is still valid."""
    return WhoAmIResponse(message=f"Hello {user.username}, your token is valid.", user_id=user.id)
