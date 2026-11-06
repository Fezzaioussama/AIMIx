"""The chats a person keeps with the assistant (the Chat screen's list): list, open,
name and delete them, and the title a new chat takes from its first message."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from api.exceptions import ValidationFailed
from api.models import CHAT_TITLE_MAX_LENGTH, Chat, User
from api.repositories import chats as repository
from api.repositories.quota import Quota


@dataclass(frozen=True)
class ChatAccess:
    """The signed-in user's chats, for one request (built in api/deps.py)."""

    session: Session
    user: User
    #: CHATS_MAX_PER_USER.
    max_chats: int


def title_of(prompt: str) -> str:
    """The first line of ``prompt``, its spaces squeezed, cut to the title's length."""
    line = next((line for line in prompt.splitlines() if line.strip()), "")
    words = " ".join(line.split())
    if len(words) <= CHAT_TITLE_MAX_LENGTH:
        return words
    return f"{words[: CHAT_TITLE_MAX_LENGTH - 1].rstrip()}…"


def list_chats(access: ChatAccess) -> list[Chat]:
    """The user's chats, the one last written to first."""
    return repository.for_user(access.session, access.user)


def open_chat(access: ChatAccess, chat_id: int) -> Chat:
    """One chat with its messages (another user's is not found)."""
    return repository.get_owned(access.session, access.user, chat_id)


def create(access: ChatAccess, title: str) -> Chat:
    quota = Quota(
        access.max_chats,
        ValidationFailed(f"You can keep up to {access.max_chats} chats. Delete one first."),
    )
    return repository.create(access.session, access.user, title, quota)


def rename(access: ChatAccess, chat_id: int, title: str) -> Chat:
    chat = repository.get_owned(access.session, access.user, chat_id)
    return repository.set_title(access.session, chat, title)


def delete(access: ChatAccess, chat_id: int) -> None:
    """Delete a chat and its messages."""
    chat = repository.get_owned(access.session, access.user, chat_id)
    repository.delete(access.session, chat)
