"""What one chat message carries: the newest prompt, what was said before it and
the person's time zone, as plain values (AGENTS.md §2)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from api.services.schedules.timing import time_zone_error

ChatRole = Literal["user", "assistant"]


@dataclass(frozen=True)
class ChatTurn:
    """One earlier message of the conversation, as the screen showed it."""

    role: ChatRole
    text: str


@dataclass(frozen=True)
class Conversation:
    """The newest message, the turns before it (oldest first), the person's
    IANA time zone (None when the browser gave none this server knows), and the
    assistant's notes on the turns before those, when a kept chat has grown past
    what it reads verbatim (``chat_memory``)."""

    prompt: str
    history: tuple[ChatTurn, ...] = ()
    timezone: str | None = None
    summary: str = ""


def known_zone(name: str | None) -> str | None:
    """``name`` when it is a time zone this server knows, else None: a browser's
    unusual zone must not stop the chat, the assistant asks for one instead."""
    if name is None or time_zone_error(name) is not None:
        return None
    return name


def recent(history: tuple[ChatTurn, ...], max_chars: int) -> tuple[ChatTurn, ...]:
    """The newest turns whose texts fit in ``max_chars`` together, oldest first,
    so a long conversation costs each new message at most that much more."""
    kept: list[ChatTurn] = []
    used = 0
    for turn in reversed(history):
        used += len(turn.text)
        if used > max_chars:
            break
        kept.append(turn)
    return tuple(reversed(kept))


def conversation_of(
    prompt: str, history: Iterable[ChatTurn], zone: str | None, max_history_chars: int
) -> Conversation:
    """What the assistant is given for one message: the prompt, the newest turns
    that fit in ``max_history_chars``, and the person's zone when it is known."""
    return Conversation(prompt, recent(tuple(history), max_history_chars), known_zone(zone))


def model_messages(conversation: Conversation) -> list[dict[str, str]]:
    """The conversation as the model reads it: the earlier turns, then the prompt."""
    return [
        *({"role": turn.role, "content": turn.text} for turn in conversation.history),
        {"role": "user", "content": conversation.prompt},
    ]
