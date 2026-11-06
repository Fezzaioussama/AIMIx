"""A person's chats with the assistant: each chat's messages, and the notes that stand
in for the older ones once they are out of the assistant's view (``services/chat_memory``)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import Base, _status_type, _utcnow

#: A chat's title: the first line of what was first asked, or what the person named it.
CHAT_TITLE_MAX_LENGTH = 100


class ChatRole(str, Enum):
    """Who said a message: the person, or the assistant."""

    USER = "user"
    ASSISTANT = "assistant"


class Chat(Base):
    """One conversation with the assistant, kept on the server so it can be opened
    again from any tab or device.

    ``summary`` is the assistant's notes on the messages up to ``summary_through_id``,
    which it reads instead of them once they no longer fit in CHAT_HISTORY_MAX_CHARS;
    empty until a chat grows that long. ``updated_at`` moves with every message.
    """

    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(CHAT_TITLE_MAX_LENGTH), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    summary_through_id: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="chat", cascade="all, delete-orphan", order_by="ChatMessage.id"
    )


class ChatMessage(Base):
    """One message of a chat. An assistant message also holds the tools its reply
    used (``{"tool", "label", "status", "detail", "action"}`` each, as the chat
    screen showed them, never a tool's arguments or output) and what its model
    calls used and cost; a person's message has none of either.
    """

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    role: Mapped[ChatRole] = mapped_column(_status_type(ChatRole))
    text: Mapped[str] = mapped_column(Text, default="")
    tools: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    #: USD, the calls whose cost is known added up; None when none is.
    cost_usd: Mapped[float | None]
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    chat: Mapped[Chat] = relationship(back_populates="messages")
