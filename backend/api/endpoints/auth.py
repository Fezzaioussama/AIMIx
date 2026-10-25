"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from api.deps import AppSettings, Auth, CurrentUser, DbSession, auth_rate_limit
from api.exceptions import NotAuthenticated
from api.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    WhoAmIResponse,
)
from api.services import accounts
from config.settings import Settings

#: Public on purpose: this is how an account comes into existence and signs in (§6).
public_router = APIRouter(tags=["auth"], dependencies=[Depends(auth_rate_limit)])
router = APIRouter(tags=["auth"])
REFRESH_COOKIE_PATH = "/api/token"


def _set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=int(settings.jwt_refresh_days * 86_400),
        path=REFRESH_COOKIE_PATH,
        secure=settings.app_env == "production",
        httponly=True,
        samesite="strict",
    )


def _refresh_cookie(request: Request, settings: Settings) -> str:
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token:
        raise NotAuthenticated("A refresh cookie was not provided.")
    return token


@public_router.post("/register", status_code=201)
def register(body: RegisterRequest, session: DbSession, settings: AppSettings) -> RegisterResponse:
    accounts.ensure_registration_allowed(settings.allow_public_registration)
    user = accounts.register(
        session, body.username, body.password, settings.password_hash_iterations
    )
    return RegisterResponse(username=user.username)


@public_router.post("/login")
def login(body: LoginRequest, response: Response, auth: Auth) -> AccessTokenResponse:
    credentials = accounts.Credentials(body.username, body.password)
    policy = accounts.sign_in_policy(auth.settings)
    tokens = accounts.sign_in(auth.session, auth.signer, credentials, policy)
    _set_refresh_cookie(response, tokens.refresh, auth.settings)
    return AccessTokenResponse(access=tokens.access)


@public_router.post("/token/refresh")
def refresh(request: Request, response: Response, auth: Auth) -> AccessTokenResponse:
    current = _refresh_cookie(request, auth.settings)
    tokens = accounts.refresh_access(auth.session, auth.signer, current)
    _set_refresh_cookie(response, tokens.refresh, auth.settings)
    return AccessTokenResponse(access=tokens.access)


@public_router.post("/token/logout", status_code=204)
def logout(request: Request, response: Response, auth: Auth) -> None:
    token = request.cookies.get(auth.settings.refresh_cookie_name)
    if token:
        accounts.revoke_refresh(auth.session, auth.signer, token)
    response.delete_cookie(
        auth.settings.refresh_cookie_name,
        path=REFRESH_COOKIE_PATH,
        secure=auth.settings.app_env == "production",
        httponly=True,
        samesite="strict",
    )


@router.get("/protected")
def protected(user: CurrentUser) -> WhoAmIResponse:
    """Cheap way for the client to confirm a token is still valid."""
    return WhoAmIResponse(message=f"Hello {user.username}, your token is valid.", user_id=user.id)
