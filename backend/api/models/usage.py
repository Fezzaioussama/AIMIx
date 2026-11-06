"""What an account's model calls outside runs used: one row per chat or planner
call, so an account's spending (runs, chats and planning) adds up by day. A run's
calls are on its steps (``RunStep``)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import MODEL_ID_MAX_LENGTH, Base, _status_type, _utcnow


class UsageKind(str, Enum):
    """What made the calls a usage event counts."""

    CHAT = "chat"
    PLANNER = "planner"


class UsageEvent(Base):
    """One model call made for an account outside a run: a chat message's, or the
    planner's. Deleting the account deletes its events."""

    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[UsageKind] = mapped_column(_status_type(UsageKind))
    model: Mapped[str] = mapped_column(String(MODEL_ID_MAX_LENGTH))
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    #: USD when known (the provider's report, else the catalogue), else None.
    cost_usd: Mapped[float | None]
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)
