"""What a person told AIMIx to keep in mind for every chat, plan and run: their standing
instructions, in their own words (Settings → Memory; ``services/user_memory``)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base, _utcnow


class UserMemory(Base):
    """One row per account, made the first time they save something."""

    __tablename__ = "user_memory"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    instructions: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)
