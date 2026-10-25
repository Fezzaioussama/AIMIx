"""Typed application settings, read from the environment and ``backend/.env``.

The single source of every tuning value, URL and credential (AGENTS.md §6).
Variables formerly prefixed ``DJANGO_`` are still accepted under that name, so
an existing ``.env`` keeps working.

``Settings`` holds the app and auth settings and composes one model per area,
each in its own module: ``llm_settings``, ``agent_settings``,
``document_settings`` and ``run_settings``. Code reads them all through
``Settings``.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from config.agent_settings import AgentSettings, HttpMCPServer, MCPServer, StdioMCPServer
from config.document_settings import MULTIPART_OVERHEAD_BYTES, DocumentSettings
from config.fields import BASE_DIR, SECRET_PLACEHOLDERS, CommaList, Secret, env_aliases
from config.llm_settings import LlmSettings
from config.run_settings import RunSettings

__all__ = [
    "BASE_DIR",
    "LOCAL_SECRET_KEY",
    "MULTIPART_OVERHEAD_BYTES",
    "SECRET_PLACEHOLDERS",
    "HttpMCPServer",
    "MCPServer",
    "Settings",
    "StdioMCPServer",
    "get_settings",
    "pin_settings",
]

#: Only acceptable when APP_ENV=local; production refuses to start without a key.
LOCAL_SECRET_KEY = "insecure-local-development-key-change-me"
#: Production floors: a guessable SECRET_KEY forges sessions, and a cheap hash
#: makes a stolen database's passwords cheap to crack (OWASP's PBKDF2 minimum).
MIN_PRODUCTION_SECRET_KEY_LENGTH = 32
MIN_PRODUCTION_HASH_ITERATIONS = 600_000


class Settings(LlmSettings, AgentSettings, DocumentSettings, RunSettings, BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        extra="ignore",
        populate_by_name=True,
    )

    app_env: Literal["local", "production", "test"] = Field("local", validation_alias="APP_ENV")
    debug: bool = Field(False, validation_alias=env_aliases("DEBUG", "DJANGO_DEBUG"))
    secret_key: Secret = Field("", validation_alias=env_aliases("SECRET_KEY", "DJANGO_SECRET_KEY"))
    # Previous SECRET_KEYs, still accepted while rotating: they verify sessions and
    # decrypt saved keys; only SECRET_KEY signs and encrypts.
    secret_key_fallbacks: CommaList = Field([], validation_alias="SECRET_KEY_FALLBACKS")
    allowed_hosts: CommaList = Field(
        ["localhost", "127.0.0.1"],
        validation_alias=env_aliases("ALLOWED_HOSTS", "DJANGO_ALLOWED_HOSTS"),
    )
    cors_allowed_origins: CommaList = Field(
        ["http://localhost:4200", "http://127.0.0.1:4200"],
        validation_alias=env_aliases("CORS_ALLOWED_ORIGINS", "DJANGO_CORS_ALLOWED_ORIGINS"),
    )
    database_url: str = Field(
        f"sqlite:///{BASE_DIR / 'aimix.sqlite3'}", validation_alias="DATABASE_URL"
    )
    log_level: str = Field("INFO", validation_alias=env_aliases("LOG_LEVEL", "DJANGO_LOG_LEVEL"))
    # Built React app (frontend/dist) to serve next to /api; empty serves none.
    frontend_dist_dir: str = Field("", validation_alias="FRONTEND_DIST_DIR")
    # Proxies in front of the app that each append to X-Forwarded-For; the client
    # is the entry this many from the right. 0 trusts no header: the socket peer.
    trusted_proxy_hops: int = Field(0, ge=0, validation_alias="TRUSTED_PROXY_HOPS")

    jwt_access_minutes: float = Field(60, gt=0, validation_alias="JWT_ACCESS_MINUTES")
    jwt_refresh_days: float = Field(1, gt=0, validation_alias="JWT_REFRESH_DAYS")
    refresh_cookie_name: str = Field(
        "aimix_refresh", min_length=1, validation_alias="REFRESH_COOKIE_NAME"
    )
    # Django 5.2's PBKDF2 work factor, so imported and new hashes match.
    password_hash_iterations: int = Field(
        1_000_000, ge=1, validation_alias="PASSWORD_HASH_ITERATIONS"
    )
    allow_public_registration: bool = Field(False, validation_alias="ALLOW_PUBLIC_REGISTRATION")
    auth_rate_limit_requests: int = Field(20, ge=1, validation_alias="AUTH_RATE_LIMIT_REQUESTS")
    auth_rate_limit_window_seconds: int = Field(
        60, ge=1, validation_alias="AUTH_RATE_LIMIT_WINDOW_SECONDS"
    )
    # Failed sign-ins one username may take per window, whatever the client.
    auth_account_failure_limit: int = Field(10, ge=1, validation_alias="AUTH_ACCOUNT_FAILURE_LIMIT")
    auth_account_failure_window_seconds: int = Field(
        900, ge=1, validation_alias="AUTH_ACCOUNT_FAILURE_WINDOW_SECONDS"
    )
    # Per account and route, for requests that make the server spend: model calls,
    # outbound calls, document parsing (api.deps.user_rate_limit).
    user_rate_limit_requests: int = Field(30, ge=1, validation_alias="USER_RATE_LIMIT_REQUESTS")
    user_rate_limit_window_seconds: int = Field(
        60, ge=1, validation_alias="USER_RATE_LIMIT_WINDOW_SECONDS"
    )

    @field_validator("log_level", mode="after")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _check_environment(self) -> Settings:
        """Fail fast on unsafe production configuration (§6)."""
        if self.app_env == "production":
            problems = [message for unsafe, message in PRODUCTION_REFUSALS if unsafe(self)]
            if problems:
                raise ValueError(" ".join(problems))
        elif not self.secret_key:
            self.secret_key = LOCAL_SECRET_KEY
        return self


#: Each configuration production refuses to start with, and why (§5 O: a new
#: check is one entry).
PRODUCTION_REFUSALS: tuple[tuple[Callable[[Settings], bool], str], ...] = (
    (lambda s: s.debug, "DEBUG must be false in production."),
    (lambda s: not s.secret_key, "SECRET_KEY must be set in production."),
    (
        lambda s: 0 < len(s.secret_key) < MIN_PRODUCTION_SECRET_KEY_LENGTH,
        f"SECRET_KEY must be at least {MIN_PRODUCTION_SECRET_KEY_LENGTH} characters in production.",
    ),
    (
        lambda s: s.secret_key == LOCAL_SECRET_KEY,
        "SECRET_KEY must not be the local development key in production.",
    ),
    (lambda s: not s.allowed_hosts, "ALLOWED_HOSTS must list at least one host."),
    (
        lambda s: s.integrations_allow_private_network,
        "INTEGRATIONS_ALLOW_PRIVATE_NETWORK must be false in production.",
    ),
    (
        lambda s: s.password_hash_iterations < MIN_PRODUCTION_HASH_ITERATIONS,
        f"PASSWORD_HASH_ITERATIONS must be at least {MIN_PRODUCTION_HASH_ITERATIONS}"
        " in production.",
    ),
)


_pinned: Settings | None = None


def get_settings() -> Settings:
    """The process-wide settings: pinned ones if set, else the environment's."""
    return _pinned or _from_environment()


def pin_settings(settings: Settings | None) -> None:
    """Fix the settings for this process (tests, one-off tools); None unpins."""
    global _pinned
    _pinned = settings


@lru_cache(maxsize=1)
def _from_environment() -> Settings:
    return Settings()
