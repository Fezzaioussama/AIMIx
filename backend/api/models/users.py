"""An account and what belongs to it alone: its rate-limit counters, its model keys and
the MCP servers it connected."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import (
    API_KEY_HINT_LENGTH,
    EMAIL_MAX_LENGTH,
    INTEGRATION_NAME_MAX_LENGTH,
    INTEGRATION_URL_MAX_LENGTH,
    MODEL_ID_MAX_LENGTH,
    PROVIDER_NAME_MAX_LENGTH,
    STATUS_MAX_LENGTH,
    TOKEN_HASH_LENGTH,
    USERNAME_MAX_LENGTH,
    Base,
    _utcnow,
)

if TYPE_CHECKING:
    from api.models.pipelines import Pipeline


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(USERNAME_MAX_LENGTH), unique=True)
    #: ``pbkdf2_sha256$<iterations>$<salt>$<hash>`` — the format Django used, so
    #: accounts imported from the previous backend keep their passwords.
    password_hash: Mapped[str] = mapped_column(String(256))
    #: SHA-256 of the one currently valid refresh token. Keeping only a hash
    #: makes refresh rotation and logout possible without storing bearer secrets.
    refresh_token_hash: Mapped[str] = mapped_column(String(64), default="")
    #: Stamped into every access token; bumping it (logout) revokes the ones issued.
    token_version: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    #: The LLM provider this user's requests go to; None means LLM_PROVIDER.
    llm_provider: Mapped[str | None] = mapped_column(String(PROVIDER_NAME_MAX_LENGTH))
    #: Where password-reset links and notifications go; None until the person gives
    #: one. Stored lower-cased, so one address opens one account.
    email: Mapped[str | None] = mapped_column(String(EMAIL_MAX_LENGTH), unique=True, index=True)
    #: Whether the account is emailed when a run ends, waits for it, or a schedule
    #: cannot start (api/services/notifications.py).
    email_notifications: Mapped[bool] = mapped_column(default=True)

    pipelines: Mapped[list[Pipeline]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    provider_settings: Mapped[list[ProviderSetting]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RateLimitBucket(Base):
    """A cross-process fixed-window counter containing no raw client address."""

    __tablename__ = "rate_limit_buckets"
    __table_args__ = (UniqueConstraint("identity_hash", "action", name="uq_rate_limit_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    identity_hash: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    window_started_at: Mapped[datetime] = mapped_column(default=_utcnow)
    hits: Mapped[int] = mapped_column(default=0)


class ProviderSetting(Base):
    """One user's API key and default model for one LLM provider.

    The key is stored encrypted (``api.security.SecretBox``) and never leaves the
    server; ``api_key_hint`` keeps its last characters so the UI can tell keys
    apart. Empty strings mean "not saved": the environment's value applies.
    """

    __tablename__ = "provider_settings"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_provider_setting_per_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(PROVIDER_NAME_MAX_LENGTH))
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    api_key_hint: Mapped[str] = mapped_column(String(API_KEY_HINT_LENGTH), default="")
    default_model: Mapped[str] = mapped_column(String(MODEL_ID_MAX_LENGTH), default="")

    user: Mapped[User] = relationship(back_populates="provider_settings")


class Integration(Base):
    """One of a user's own MCP servers, reached over streamable HTTP only.

    Header values are stored encrypted as one JSON object
    (``api.security.SecretBox``) and never leave the server; ``header_hints``
    keeps each header's name and a short hint of its value, as
    ``{"name", "hint"}`` objects, so the UI can tell them apart.
    """

    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_integration_name_per_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(INTEGRATION_NAME_MAX_LENGTH))
    url: Mapped[str] = mapped_column(String(INTEGRATION_URL_MAX_LENGTH))
    headers_encrypted: Mapped[str] = mapped_column(Text, default="")
    header_hints: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(default=True)
    #: Its tools wait for the run owner's OK before they act (approval gates).
    require_approval: Mapped[bool] = mapped_column(default=True)
    #: The OAuth sign-in to the server (``services/integrations/oauth``): "" (none),
    #: "pending" (the owner is signing in) or "connected". The attempt, then the tokens,
    #: are sealed in ``oauth_encrypted``; ``oauth_state_hash`` finds the integration when
    #: the authorization server calls back, and is cleared once it has.
    oauth_status: Mapped[str] = mapped_column(String(STATUS_MAX_LENGTH), default="")
    oauth_encrypted: Mapped[str] = mapped_column(Text, default="")
    oauth_state_hash: Mapped[str | None] = mapped_column(
        String(TOKEN_HASH_LENGTH), unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
