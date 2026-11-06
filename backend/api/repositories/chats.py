"""Data access for a person's chats and their messages (AGENTS.md §7 Repository).

Every lookup is by owner, so another account's chat looks exactly like one that
does not exist. Each write commits its own transaction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from api.exceptions import NotFound
from api.models import Chat, ChatMessage, ChatRole, User
from api.repositories.quota import Quota, enforce, lock_owner
from llm.usage import NO_USAGE, TokenUsage


@dataclass(frozen=True)
class MessageDraft:
    """One message to add to a chat: who said it, what, and (the assistant's) the
    tools the reply used and what its model calls used."""

    role: ChatRole
    text: str
    tools: list[dict[str, Any]] = field(default_factory=list)
    usage: TokenUsage = NO_USAGE


def _owned_by(user: User) -> Select[tuple[Chat]]:
    return select(Chat).where(Chat.user_id == user.id)


def for_user(session: Session, user: User) -> list[Chat]:
    """The user's chats, the one last written to first; their messages are not loaded."""
    return list(session.scalars(_owned_by(user).order_by(Chat.updated_at.desc(), Chat.id.desc())))


def all_for_user(session: Session, user: User) -> list[Chat]:
    """Every chat with its messages, the newest first: the data export."""
    query = _owned_by(user).options(selectinload(Chat.messages)).order_by(Chat.id.desc())
    return list(session.scalars(query))


def get_owned(session: Session, user: User, chat_id: int) -> Chat:
    chat = session.scalar(_owned_by(user).where(Chat.id == chat_id))
    if chat is None:
        raise NotFound(f"Chat {chat_id} was not found.")
    return chat


def create(session: Session, user: User, title: str, quota: Quota) -> Chat:
    """A new chat, while the user stays within ``quota``."""
    lock_owner(session, user.id)
    chat = Chat(user_id=user.id, title=title)
    session.add(chat)
    count = select(func.count()).select_from(Chat).where(Chat.user_id == user.id)
    enforce(session, count, quota)
    session.commit()
    session.refresh(chat)
    return chat


def set_title(session: Session, chat: Chat, title: str) -> Chat:
    chat.title = title
    session.commit()
    session.refresh(chat)
    return chat


def delete(session: Session, chat: Chat) -> None:
    session.delete(chat)
    session.commit()


def count_messages(session: Session, chat: Chat) -> int:
    query = select(func.count()).select_from(ChatMessage).where(ChatMessage.chat_id == chat.id)
    return session.scalar(query) or 0


def messages_after(session: Session, chat: Chat, after_id: int | None) -> list[ChatMessage]:
    """The chat's messages past ``after_id`` (all of them for None), oldest first."""
    query = select(ChatMessage).where(ChatMessage.chat_id == chat.id)
    if after_id is not None:
        query = query.where(ChatMessage.id > after_id)
    return list(session.scalars(query.order_by(ChatMessage.id)))


def add_message(session: Session, chat: Chat, draft: MessageDraft, now: datetime) -> ChatMessage:
    """Append ``draft`` to the chat, which counts as written to at ``now``."""
    message = ChatMessage(
        chat_id=chat.id,
        role=draft.role,
        text=draft.text,
        tools=draft.tools,
        input_tokens=draft.usage.input_tokens,
        output_tokens=draft.usage.output_tokens,
        cost_usd=draft.usage.cost_usd,
    )
    chat.updated_at = now
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


def set_summary(session: Session, chat: Chat, summary: str, through_id: int) -> None:
    """The notes that now stand in for the messages up to ``through_id``."""
    chat.summary = summary
    chat.summary_through_id = through_id
    session.commit()
