"""What the assistant remembers of a chat between messages: the Chat screen's
conversations, kept on the server (``models/chat``).

Before a reply, the assistant reads the chat's newest messages that fit in
CHAT_HISTORY_MAX_CHARS together, as it always did. The older ones, instead of
falling out of its view, are folded once into notes it writes itself
(``ChatAgent.summarize``, at most CHAT_SUMMARY_MAX_CHARS), kept with the chat and
read with every later message in their place: a compaction after Celia Agent's,
with the model writing the notes. After the reply, both sides of the exchange
are saved, with the tools the reply used and what its model calls used.

Every database access is a short transaction of its own: the request's session
may be closed while a reply still streams.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any

from anyio import to_thread

from api.db import Database
from api.exceptions import ChatFull
from api.models import ChatRole, User
from api.repositories import chats as repository
from api.repositories.chats import MessageDraft
from api.services.chat import ChatAgent
from api.services.chat_conversation import (
    ChatTurn,
    Conversation,
    conversation_of,
    known_zone,
    recent,
)
from api.services.chat_events import ChatEvent
from api.services.chats import title_of
from api.services.run_recorder import utcnow
from llm.usage import NO_USAGE, TokenUsage


@dataclass(frozen=True)
class ChatOpening:
    """One message as POST /chat receives it: for a kept chat, or with its own history."""

    prompt: str
    chat_id: int | None = None
    history: tuple[ChatTurn, ...] = ()
    timezone: str | None = None


@dataclass(frozen=True)
class MemoryLimits:
    #: CHAT_HISTORY_MAX_CHARS: what the assistant reads verbatim; 0 is nothing.
    history_max_chars: int
    #: CHAT_SUMMARY_MAX_CHARS: how long its notes may be.
    summary_max_chars: int
    #: CHAT_MAX_MESSAGES: how many messages one chat may hold.
    max_messages: int


def _turn(role: ChatRole, text: str) -> ChatTurn:
    return ChatTurn("user" if role is ChatRole.USER else "assistant", text)


class ReplyRecorder:
    """Folds a reply's events into the message to save: its text, the tools it used
    (a result closes the newest run of its tool, as the chat screen shows them) and
    what its model calls used."""

    def __init__(self) -> None:
        self._text: list[str] = []
        self._tools: list[dict[str, Any]] = []
        self._usage: TokenUsage = NO_USAGE

    def take(self, event: ChatEvent) -> None:
        if event.kind == "text":
            self._text.append(event.text)
        elif event.kind == "tool":
            self._take_tool(event)
        elif event.usage is not None:
            self._usage = event.usage

    def _take_tool(self, event: ChatEvent) -> None:
        if event.status == "started":
            self._tools.append(self._tool(event))
            return
        running = next(
            (
                tool
                for tool in reversed(self._tools)
                if tool["tool"] == event.tool and tool["status"] == "started"
            ),
            None,
        )
        if running is None:
            self._tools.append(self._tool(event))
            return
        running.update(status=event.status, detail=event.detail, action=event.action)

    @staticmethod
    def _tool(event: ChatEvent) -> dict[str, Any]:
        return {
            "tool": event.tool,
            "label": event.label,
            "status": event.status,
            "detail": event.detail,
            "action": event.action,
        }

    def draft(self) -> MessageDraft:
        return MessageDraft(ChatRole.ASSISTANT, "".join(self._text), self._tools, self._usage)


@dataclass(frozen=True)
class ChatMemory:
    """The signed-in user's kept chats, as the chat endpoint uses them (api/deps.py)."""

    database: Database
    user: User
    limits: MemoryLimits

    async def open(self, opening: ChatOpening, agent: ChatAgent) -> Conversation:
        """What the assistant is given for this message. For a kept chat: the newest
        messages that fit, and its notes on the rest, brought up to date first."""
        if opening.chat_id is None:
            return conversation_of(
                opening.prompt, opening.history, opening.timezone, self.limits.history_max_chars
            )
        summary, messages = await to_thread.run_sync(self._unread, opening.chat_id)
        turns = tuple(_turn(message.role, message.text) for message in messages)
        kept = recent(turns, self.limits.history_max_chars)
        older = messages[: len(messages) - len(kept)]
        if older and self.limits.history_max_chars:
            summary = await self._fold(agent, summary, turns[: len(older)])
            await to_thread.run_sync(self._keep_summary, opening.chat_id, summary, older[-1].id)
        elif not self.limits.history_max_chars:
            # Each message stands alone: the notes are not read either.
            summary = ""
        return Conversation(opening.prompt, kept, known_zone(opening.timezone), summary)

    def recorded(
        self, chat_id: int | None, prompt: str, events: AsyncIterator[ChatEvent]
    ) -> AsyncIterator[ChatEvent]:
        """``events`` as they are, saving the exchange to the chat when there is one."""
        return events if chat_id is None else self._record(chat_id, prompt, events)

    async def _record(
        self, chat_id: int, prompt: str, events: AsyncIterator[ChatEvent]
    ) -> AsyncIterator[ChatEvent]:
        # The reply has begun (its first text arrived), so both sides are kept.
        await to_thread.run_sync(self._save, chat_id, MessageDraft(ChatRole.USER, prompt))
        reply = ReplyRecorder()
        try:
            async for event in events:
                reply.take(event)
                yield event
        except GeneratorExit:
            # The person left mid-reply: what came is kept (nothing can be awaited here).
            self._save(chat_id, reply.draft())
            raise
        await to_thread.run_sync(self._save, chat_id, reply.draft())

    def _unread(self, chat_id: int) -> tuple[str, list[Any]]:
        """The chat's notes, and the messages they do not cover yet."""
        with self.database.session() as session:
            chat = repository.get_owned(session, self.user, chat_id)
            if repository.count_messages(session, chat) + 2 > self.limits.max_messages:
                raise ChatFull("This chat is full: start a new chat to go on.")
            messages = repository.messages_after(session, chat, chat.summary_through_id)
            session.expunge_all()
            return chat.summary, messages

    async def _fold(self, agent: ChatAgent, summary: str, turns: Sequence[ChatTurn]) -> str:
        notes = await agent.summarize(summary, turns, self.limits.summary_max_chars)
        return notes.strip()[: self.limits.summary_max_chars]

    def _keep_summary(self, chat_id: int, summary: str, through_id: int) -> None:
        with self.database.session() as session:
            chat = repository.get_owned(session, self.user, chat_id)
            repository.set_summary(session, chat, summary, through_id)

    def _save(self, chat_id: int, draft: MessageDraft) -> None:
        with self.database.session() as session:
            chat = repository.get_owned(session, self.user, chat_id)
            if not chat.title and draft.role is ChatRole.USER:
                chat.title = title_of(draft.text)
            repository.add_message(session, chat, draft, utcnow())
