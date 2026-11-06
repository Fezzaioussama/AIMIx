"""Authentication endpoints: accounts, sign-in, tokens, and the password reset by link."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from api.account_deps import PasswordResets
from api.deps import AppSettings, Auth, CurrentUser, DbSession
from api.exceptions import NotAuthenticated
from api.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    RegisterResponse,
    WhoAmIResponse,
)
from api.services import account_data, accounts, password_reset
from api.throttling import auth_rate_limit, registration_rate_limit
from config.settings import Settings

#: Public on purpose: this is how an account comes into existence and signs in (§6).
public_router = APIRouter(tags=["auth"], dependencies=[Depends(auth_rate_limit)])
router = APIRouter(tags=["auth"])
REFRESH_COOKIE_PATH = "/api/token"


def set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=int(settings.jwt_refresh_days * 86_400),
        path=REFRESH_COOKIE_PATH,
        secure=settings.app_env == "production",
        httponly=True,
        samesite="strict",
    )


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.refresh_cookie_name,
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


@public_router.post("/register", status_code=201, dependencies=[Depends(registration_rate_limit)])
def register(body: RegisterRequest, session: DbSession, settings: AppSettings) -> RegisterResponse:
    accounts.ensure_registration_allowed(settings.allow_public_registration)
    credentials = accounts.Credentials(body.username, body.password, body.email)
    user = account_data.open_account(session, settings, credentials)
    return RegisterResponse(username=user.username)


@public_router.post("/login")
def login(body: LoginRequest, response: Response, auth: Auth) -> AccessTokenResponse:
    credentials = accounts.Credentials(body.username, body.password)
    policy = accounts.sign_in_policy(auth.settings)
    tokens = accounts.sign_in(auth.session, auth.signer, credentials, policy)
    set_refresh_cookie(response, tokens.refresh, auth.settings)
    return AccessTokenResponse(access=tokens.access)


@public_router.post("/token/refresh")
def refresh(request: Request, response: Response, auth: Auth) -> AccessTokenResponse:
    current = _refresh_cookie(request, auth.settings)
    tokens = accounts.refresh_access(auth.session, auth.signer, current)
    set_refresh_cookie(response, tokens.refresh, auth.settings)
    return AccessTokenResponse(access=tokens.access)


@public_router.post("/token/logout", status_code=204)
def logout(request: Request, response: Response, auth: Auth) -> None:
    token = request.cookies.get(auth.settings.refresh_cookie_name)
    if token:
        accounts.revoke_refresh(auth.session, auth.signer, token)
    clear_refresh_cookie(response, auth.settings)


@public_router.post("/password-reset", status_code=204)
def request_password_reset(body: PasswordResetRequest, flow: PasswordResets) -> None:
    """Emails a reset link to the account using this address, if any: 204 either way."""
    password_reset.request_reset(flow, body.email)


@public_router.post("/password-reset/confirm", status_code=204)
def confirm_password_reset(body: PasswordResetConfirm, flow: PasswordResets) -> None:
    """Replaces the password of the account the link's token names, once."""
    confirmation = password_reset.ResetConfirmation(body.token, body.password)
    password_reset.confirm_reset(flow, confirmation)


@router.get("/protected")
def protected(user: CurrentUser) -> WhoAmIResponse:
    """Cheap way for the client to confirm a token is still valid, and whose it is."""
    return WhoAmIResponse(
        message=f"Hello {user.username}, your token is valid.",
        user_id=user.id,
        username=user.username,
    )
